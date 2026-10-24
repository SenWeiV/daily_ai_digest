## Why

Code review found that failed or partially accepted email can be reported as success, unsent records suppress later delivery, and the previous-day label does not constrain discovery. The dashboard also fetches the same latest record regardless of the selected digest type.

## What Changes

- Track delivery outcomes, retry only definitively unsent records, and preserve uncertain outcomes for operator review.
- Apply timezone-aware content windows to discovery, including bounded historical arXiv queries and GitHub activity filters.
- Bound Trending latency, require an AI signal for generic Agent vocabulary, and load the selected digest type in the UI.
- Correct dynamic attachment budgeting and provide an HTTPS API entry point using the connected owned Cloudflare domain.
- Add a production-like isolated email acceptance run and exact-message read-only IMAP verification.
- Validate locally, back up and deploy the service, send one test email, and push reviewed source changes.

## Capabilities

### New Capabilities
- `digest-delivery-integrity`: Accurate persisted delivery outcomes and isolated end-to-end acceptance.
- `digest-content-window`: Explicit business-timezone windows for source discovery.
- `digest-type-navigation`: Type-specific latest and dated record retrieval.

### Modified Capabilities

None. Existing topic coverage and A/B/C selection priorities remain applicable.

## Impact

Backend orchestration, SQLite migration, SMTP handling, source agents, read APIs, React data loading, regression tests, operator scripts, and a dedicated Cloudflare Worker. No dependency upgrade or permanent image-feature enablement is required.
