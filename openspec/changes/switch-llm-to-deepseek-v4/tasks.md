# Implementation Tasks

## 1. Confirm the provider facts before editing

- [x] 1.1 Call `GET https://api.deepseek.com/models` with the real DeepSeek key and confirm `deepseek-v4-flash` is present. **Partially closed.** The host is reachable (HTTP 401 in 0.5s, so TLS and routing are fine), but no DeepSeek credential exists in this environment — the only key present authenticates against neither `api.deepseek.com` nor either Moonshot host. `deepseek-v4-flash` was instead confirmed against DeepSeek's own pricing documentation, which names it with version `DeepSeek-V4-Flash-0731` at $0.14 input / $0.28 output per M and 1M context. **This must still be run with the real key before the server switch** (task 4.2).
- [x] 1.2 Record the observed model list, the resolved endpoint form, and whether the response exposes a `usage` block, in the task notes below. See Notes.

## 2. Configuration

- [x] 2.1 Change the `text_model` default to `deepseek-v4-flash` and the `text_base_url` default to `https://api.deepseek.com` in `backend/app/config.py`.
- [x] 2.2 Rename the text-role variables to `TEXT_*` and keep `GEMINI_*` as a one-way fallback source (role-named name wins). **Supersedes the earlier "add a `GEMINI_TEMPERATURE` setting" task** — no temperature setting exists any more; see 3.1.
- [x] 2.3 Update `backend/.env.example` and `.env.example.docker` so DeepSeek is the active default under the `TEXT_*` names, and state that no temperature or output-cap setting is offered, with the reason.
- [x] 2.4 Update `docker-compose.yml` to pass `TEXT_*` with DeepSeek defaults and to forward the legacy `GEMINI_*` names empty-by-default so an un-migrated `.env` still resolves.
- [x] 2.5 Update `setup-server.sh`, `DOCKER_DEPLOY_GUIDE.md`, and `README.md` to name DeepSeek V4 Flash as the default with correct pricing, and keep Kimi and the others as alternatives.
- [x] 2.6 Add tests for the configuration defaults.

## 3. Request path

- [x] 3.1 Send only `model` and `messages`. The hardcoded `temperature: 1` and `max_tokens: 8192` are both gone, and no configured replacement was introduced — every generation parameter takes the provider default, which keeps thinking mode on. Verified live: a bare request to `deepseek-v4-flash` returns 200 with `content` and `reasoning_content` both populated, `reasoning_tokens: 38`.
- [x] 3.2 Collapse the endpoint builder to two cases and verify both documented DeepSeek base URL forms plus a trailing-slash form resolve to a single `/v1/chat/completions`. Extracted as `_resolve_endpoint()`.
- [x] 3.3 Extract only `content` from the response. When `content` is empty and `reasoning_content` is present, raise a request failure and log the reasoning length at debug level without logging the trace itself.
- [x] 3.4 Include the resolved model identifier and endpoint host in the analyzer's initialization log line.
- [x] 3.5 Add tests: endpoint construction for all three base URL forms, body carries exactly `{model, messages}`, no output cap, legacy `GEMINI_*` still resolves, role-named name wins, content-plus-reasoning returns only content, empty-content-with-reasoning raises, structured part list joins correctly. 18 tests in `backend/tests/test_llm_provider.py`.

## 4. Verification and rollout

- [x] 4.1 Run the backend test suite and a Python compile check. 74 passed.
- [ ] 4.2 Back up `/opt/daily_ai_digest/data/digest.db` and record the current image tag. Update the server `.env` to the `TEXT_*` names, rebuild and restart the backend, then read back the container's resolved `TEXT_MODEL` and `TEXT_BASE_URL` and the analyzer startup log line. **Task 1.1's `GET /models` is now closed with the real key — see the note below — but re-run it from the server so the check covers the server's egress path too.**
- [ ] 4.3 Run one `force=true, send_email=false` digest. Record item counts, grade distribution, how many items have populated `summary` and `why_trending`, wall-clock duration, and token usage if exposed. Compare against the most recent Kimi-era digest and report the comparison rather than asserting parity.
- [ ] 4.4 Confirm the next scheduled daily run is still registered. If the comparison in 4.3 shows a quality regression, restore the previous `.env` and image tag and report before proceeding.

## Notes

Task 1.1 is a hard gate: the model id is corroborated across DeepSeek's pricing page and several independent provider catalogs, but `api-docs.deepseek.com` was not directly reachable during planning, so it has not been confirmed against the authoritative API.

**Task 1.1 closed with the real key (2026-08-01).** `GET https://api.deepseek.com/models` with the operator-supplied `TEXT_API_KEY` returns exactly two ids: `deepseek-v4-flash` and `deepseek-v4-pro`. No legacy alias (`deepseek-chat`, `deepseek-reasoner`) is listed, so the id in configuration is the only correct spelling. A bare `POST /chat/completions` carrying only `model` and `messages` returned HTTP 200 with `content: "好"`, a populated `reasoning_content`, `completion_tokens_details.reasoning_tokens: 38`, and `finish_reason: "stop"`. This settles the open question below: the response **does** carry a `usage` block with reasoning token counts.

**Task 1.2 record (local, 2026-08-01):** `https://api.deepseek.com/models` answers in ~0.5s from this machine. Resolved endpoint form is `https://api.deepseek.com/v1/chat/completions` for all three documented base-URL spellings (asserted by test). The `usage` block is present and includes `completion_tokens_details.reasoning_tokens`; the analyzer's token counter remains the pre-existing `len//4` estimate, so nothing depends on it yet, but a real per-run figure is now obtainable.

Task 4.3 is a report, not a pass/fail assertion. The purpose is to make a prompt-quality regression visible before the daily email depends on the new model, not to claim the two models are equivalent.

**Credential warning for the operator:** the switch is breaking on the key, not just the model name. The server's text credential currently holds a Moonshot key, which returns `authentication_error` against `api.deepseek.com`. Rotating the base URL without rotating the key produces a run where every item fails analysis while collection still succeeds — a digest that arrives looking thin rather than broken. The variables are now `TEXT_*`; `GEMINI_*` still resolves as a fallback, so an un-migrated `.env` keeps working, but a *half*-migrated one where `TEXT_API_KEY` is set empty does not fall back — an empty new name is treated as unset, which is why the fallback keys on empty string rather than on absence.
