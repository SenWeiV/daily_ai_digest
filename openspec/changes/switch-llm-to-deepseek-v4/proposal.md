## Why

The digest currently runs on Kimi `kimi-k2.5` through the OpenAI-compatible path. DeepSeek V4 Flash is roughly an order of magnitude cheaper per token, exposes a 1M-token context and 384K max output, and is reachable directly from the mainland Baidu Cloud host. The upcoming long-image and social-draft work will multiply per-run token spend, so the model swap should land first and independently.

A second, less obvious reason: the OpenAI-compatible request path hardcodes `temperature: 1` with a comment claiming Kimi requires it. That value is not a DeepSeek requirement, and DeepSeek ignores `temperature` entirely while thinking mode is on. Leaving the hardcode in place would silently misrepresent what the request actually does.

## What Changes

- Point the LLM configuration at DeepSeek: model `deepseek-v4-flash`, base URL `https://api.deepseek.com`.
- **BREAKING** for operators: the text-role variables are renamed to `TEXT_*` (old `GEMINI_*` names still resolve as a fallback) and the key must be a DeepSeek one. A Kimi key will fail authentication against the DeepSeek host. No fallback model is retained, per the decision to run DeepSeek alone.
- Replace the hardcoded `temperature: 1` with a configurable value that defaults to a low temperature suitable for analysis, and document that DeepSeek ignores it unless thinking mode is explicitly disabled.
- Make the request path resilient to DeepSeek's response shape, including the `reasoning_content` field that thinking-mode responses carry alongside `content`.
- Update the environment templates, Compose defaults, and deployment guide so the DeepSeek values are the documented default rather than a commented-out alternative.
- Define the server rollout: verify connectivity from the container, run one no-email digest to compare output quality against the Kimi baseline, then enable the scheduled run.

Non-goals: no change to prompts, to the A/B/C grading rules, to source collection, or to the email template. Prompt quality under a new model is observed and reported, not tuned in this change.

## Capabilities

### New Capabilities

- `llm-provider-configuration`: Which model and endpoint the digest calls, how request parameters are chosen and which are ignored by the provider, how thinking-mode responses are parsed, and how a provider misconfiguration surfaces rather than silently degrading.

### Modified Capabilities

None. The existing `research-content-discovery`, `digest-quality-selection`, `arxiv-digest-source`, `github-trending-discovery`, and `github-social-proof-selection` requirements are provider-agnostic and keep their current contracts.

## Impact

- Backend: `app/config.py` (model, base URL, new temperature setting), `app/agents/gemini_analyzer.py` (request payload, response parsing).
- Configuration: `backend/.env.example`, `.env.example.docker`, `docker-compose.yml`, `setup-server.sh`, `DOCKER_DEPLOY_GUIDE.md`, `README.md`.
- Operations: server `.env` secret rotation, container restart, one verification run.
- Tests: request payload construction, thinking-mode response parsing, configuration defaults.
- Cost: per-run LLM spend drops substantially; the exact figure depends on how many candidates survive selection.
