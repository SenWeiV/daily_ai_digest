## Context

The analyzer at `backend/app/agents/gemini_analyzer.py` is named for Gemini but has been running Kimi `kimi-k2.5` through an OpenAI-compatible path since the provider switch. The class keeps two branches: a native `google.generativeai` path used when `GEMINI_BASE_URL` is empty, and an `httpx` OpenAI-compatible path used when it is set. Production has `GEMINI_BASE_URL` set, so only the second branch runs.

Three details in the current implementation matter for this change:

- `_generate_with_openai_compatible` hardcodes `temperature: 1` with the comment "Kimi API 只接受 temperature=1". That constraint belonged to a specific Kimi endpoint and does not describe DeepSeek.
- The endpoint builder has three branches that all produce the same result for a base URL ending in `/v1` and for any other non-empty path. Only a genuinely empty path gets `/v1` appended. This happens to work for both DeepSeek forms but the redundancy hides that fact.
- Response parsing reads `choices[0].message.content` and handles a list-of-parts shape. It does not know about `reasoning_content`, which DeepSeek thinking-mode responses carry.

The environment variables were originally left as `GEMINI_*` on the grounds that a rename risked breaking the deployment if any one file were missed. That reasoning was reversed once the second and third model roles landed: with `VISION_*` and `IMAGE_GEN_*` sitting beside it, a text role named after a vendor it does not use is a live source of operator error — picking the wrong endpoint for the wrong role is exactly the mistake the three-role split exists to prevent. The variables are now `TEXT_*`, and the original risk is handled directly rather than avoided: `GEMINI_*` remains an accepted fallback source, with the role-named variable winning when both are set. A missed file therefore degrades to "still works under the old name", not to "credential is empty".

That fallback is worth the extra code because the failure it prevents is quiet. An empty text credential does not stop the digest: collection succeeds, every item's analysis fails, and the email arrives on schedule looking merely thin. In an inbox that is close to invisible.

Verified model facts, from DeepSeek's published pricing and independent provider listings as of 2026-08: the model id is `deepseek-v4-flash`, it is a 284B-parameter MoE with 13B active, the context window is 1M tokens, and input/output pricing is $0.14 / $0.28 per million tokens. `deepseek-v4-pro` is the higher-capability sibling at $0.435 / $0.87. I could not fetch `api-docs.deepseek.com` directly from this environment; the model id and pricing are corroborated across DeepSeek's own pricing page as indexed and several independent provider catalogs, but the exact current status of legacy aliases like `deepseek-chat` is not something I verified first-hand. Task 1.1 confirms the id against the live `/models` endpoint before anything else changes.

## Goals / Non-Goals

**Goals:**

- Run the digest on `deepseek-v4-flash` with configuration as the only thing an operator has to change.
- Stop misrepresenting the sampling temperature; stop sending generation parameters at all and let every one of them take the provider default.
- Parse thinking-mode responses correctly so a reasoning trace never becomes a project summary.
- Roll out to the server with a quality comparison against the Kimi baseline before the scheduled run depends on it.

**Non-Goals:**

- Removing the native `google.generativeai` branch. It is dormant and harmless; deleting it is unrelated cleanup.
- Retaining or building a cross-provider fallback. The decision was DeepSeek alone.
- Tuning prompts for the new model. Quality is observed and reported; changes to prompts are a separate change if the comparison shows a regression.
- Enabling or configuring thinking mode. Default behavior is accepted as-is.

## Decisions

**Configuration-only swap, no code path for provider selection.** The OpenAI-compatible branch already handles DeepSeek; it needs a different model string and host. Adding a provider abstraction would be speculative generality for a single-provider deployment. Alternative considered: a `LLM_PROVIDER` enum with per-provider request builders. Rejected because there is exactly one provider and the differences that matter (temperature semantics, reasoning field) are better handled as tolerant parsing than as provider branches.

**Send only `model` and `messages`; no generation parameters at all.** An earlier revision of this change added a `GEMINI_TEMPERATURE` setting defaulting to 0.3, reasoning that the provider default of 1.0 is wrong for factual JSON extraction. That was reversed, and the reversal is empirically grounded rather than stylistic. A bare `POST /chat/completions` carrying only `model` and `messages` was verified live against `deepseek-v4-flash`: it returns 200 with both `content` and `reasoning_content` populated and `reasoning_tokens: 38`, so thinking mode is on by default and stays on precisely because nothing is sent to constrain it. Adding parameters back has two concrete costs. `max_tokens: 8192` truncates the answer on a long README, and because a truncated JSON body fails to parse, `analyze_github_repo` records it as an empty analysis rather than as an error — the failure is invisible. An explicit `temperature` is rejected outright by some models in this codebase's own fleet: `kimi-k3` answers `invalid temperature: only 1 is allowed for this model` with HTTP 400, and on the vision role that 400 becomes `VisionUnavailable`, which withholds every platform image rather than one. Determinism for the analysis task is therefore pursued through prompt constraints on the output format, not through a sampling constant we would be guessing on the provider's behalf. If a future task genuinely needs low-variance sampling, the correct place is the provider console or a different model, not a hardcoded field.

**Simplify the endpoint builder to two cases.** Strip trailing slashes, then append `/chat/completions` if the path already ends in `/v1`, else append `/v1/chat/completions`. This is what the current three branches compute, written once. Both documented DeepSeek base URLs resolve correctly.

**Treat `reasoning_content` as a diagnostic, never as content.** Read `content`; if it is empty and `reasoning_content` is present, raise so the existing retry and per-item failure handling applies. The risk being defended against is specific: `analyze_github_repo` falls back to `raw_fallback[:300]` when JSON parsing fails, so a reasoning trace that reached the parser would be silently truncated into the `summary` field and emailed as if it were analysis. Logging the reasoning length at debug level makes the failure diagnosable without putting the trace in the digest.

**No fallback chain, and the absence is deliberate.** `TEXT_FALLBACK_MODELS` stays empty. If DeepSeek is down, per-item analysis fails, `is_available` returns false, and the digest still generates from source metadata with truncated descriptions as summaries — the existing degradation path. The alternative, keeping Kimi as a fallback, does not work without code changes: the model loop swaps only the model name, reusing one API key and one base URL, so a Kimi model name would be sent to the DeepSeek host with a DeepSeek key. Making cross-provider fallback real means per-model credentials, which is more machinery than the current requirement justifies. Recorded here so the empty setting reads as a decision rather than an oversight.

**Verify the model id against the live endpoint before editing anything.** The id is corroborated across sources but not confirmed from the authoritative API in this environment. A wrong id fails at request time with an opaque error. `GET /models` with the real key settles it in one call, and it doubles as the credential check.

## Risks / Trade-offs

- **The model id is wrong or has been superseded** → Task 1.1 lists models from the live endpoint before any file changes. If `deepseek-v4-flash` is absent, stop and report rather than guessing at a variant.
- **Output quality regresses versus Kimi on Chinese-language analysis** → Task 4.2 runs a no-email digest and compares field-by-field against a stored Kimi-era digest. If the comparison shows a regression, report it and stop; do not tune prompts inside this change.
- **JSON adherence differs between the two models** → The parser already tolerates fenced blocks and falls back to raw text. The verification run checks whether `summary` and `why_trending` are populated across all items rather than sampling one.
- **Thinking mode makes runs slower or more expensive than the headline price implies** → Reasoning tokens bill as output. The verification run records wall-clock duration and, if the response exposes usage, token counts, so the real per-run cost is measured rather than assumed from the price table.
- **The server `.env` is edited by hand and drifts from the templates** → The rollout reads back the container's resolved environment after restart instead of trusting the edit.
- **A cheap model with a 1M context invites sending more input than necessary** → Out of scope here. Prompt truncation limits stay as they are; noted so the temptation is explicit.

## Migration Plan

1. Confirm `deepseek-v4-flash` exists via `GET https://api.deepseek.com/models` with the new key.
2. Land the code and configuration changes with tests, on a branch.
3. On the server: back up `/opt/daily_ai_digest/data/digest.db` and record the current image tag for rollback.
4. Update the server `.env` with the DeepSeek key, model, and base URL.
5. Rebuild and restart the backend container; read back the resolved environment and the analyzer's startup log line.
6. Run one `force=true, send_email=false` digest. Compare item counts, grade distribution, and populated analysis fields against the last Kimi-era digest. Record duration.
7. If the comparison is acceptable, leave the daily schedule in place and confirm the next fire time. If not, restore the previous `.env` and image tag — the swap is configuration plus a container restart, so rollback is a minute of work and touches no data.

## Open Questions

- Does the DeepSeek response include a `usage` block with reasoning token counts? If so the verification run should record it to get a real cost-per-run figure. Determined during task 4.2, not blocking.
- Should `deepseek-v4-pro` be used for the daily period summary, which is one call per run over already-analyzed items and where quality is most visible? Deferred; this change establishes the single-model baseline first.
