# Implementation Tasks

## 1. Discovery contracts and configuration

- [x] 1.1 Add research profiles, domain/content-type matching helpers, new-project window, bounded channel limits, arXiv categories, `TARGET_ITEMS=10`, and `MAX_ITEMS=24` settings with backward-compatible defaults.
- [x] 1.2 Add source-neutral candidate metadata, evidence flags, stable keys, quality grade, and explicit GitHub/arXiv relation models.
- [x] 1.3 Add unit tests for profile matching, broad-term rejection, evidence extraction, and deterministic stable keys.

## 2. GitHub discovery upgrade

- [x] 2.1 Refactor GitHub discovery to retain Trending and add bounded recently-created Repository Search queries for each narrow research profile.
- [x] 2.2 Add the recently-updated research channel for paper-linked, benchmark, dataset, evaluation, and implementation repositories.
- [x] 2.3 Fetch enough repository metadata to evaluate README, Topics, implementation, tests/examples, artifacts, and explicit paper links; reject unrelated fallback Trending projects.
- [x] 2.4 Merge and deduplicate GitHub channel results by numeric repository ID and extract explicit arXiv relations from repository metadata/README.
- [x] 2.5 Add tests for new-project value evidence, channel deduplication, query bounds, no unrelated fallback, and explicit relation extraction.

## 3. arXiv source

- [x] 3.1 Implement the arXiv RSS/Atom agent for configured categories with timeouts, bounded retrieval, XML parsing, logging, and per-feed failure isolation.
- [x] 3.2 Normalize arXiv IDs and versions, merge cross-category duplicates, retain timestamps/categories, and extract explicit GitHub relations.
- [x] 3.3 Add the arXiv item schema and source-specific analysis fields for problem, method, evaluation, results, limitations, and repository links.
- [x] 3.4 Add parser, normalization, category deduplication, failure isolation, and relation extraction tests.

## 4. Quality selection and digest orchestration

- [x] 4.1 Implement explicit A/B/C grading from relevance and evidence rules without daily score-distribution fitting.
- [x] 4.2 Implement deterministic target/max selection: all A up to 24, B only to fill target 10, never C filler, with topic/source coverage tie-breakers.
- [x] 4.3 Update digest orchestration to collect GitHub and arXiv in parallel, select before deep analysis, and preserve the existing YouTube call and output behavior.
- [x] 4.4 Add tests for all dynamic-count examples, stable ordering, source-aware deduplication, deep-analysis call bounds, and YouTube regression behavior.

## 5. Persistence and presentation

- [x] 5.1 Add additive SQLite persistence for nullable/JSON-compatible arXiv data and compatibility reads for legacy rows.
- [x] 5.2 Update API schemas/routes and historical responses to expose arXiv data and selected dynamic counts.
- [x] 5.3 Add paper-specific analyzer prompt/response handling that does not invent missing results.
- [x] 5.4 Add a distinct arXiv section to email rendering and frontend types/views without changing YouTube rendering.
- [x] 5.5 Add database migration/legacy-row, API serialization, email rendering, and frontend type tests/build checks.

## 6. Verification and production deployment

- [x] 6.1 Run backend tests, frontend tests/typecheck/build, lint/format checks, and a production-like local digest with mocked external services.
- [x] 6.2 Update deployment templates and operational documentation with new non-secret settings and the selected deployment procedure.
- [ ] 6.3 Verify the live Baidu host and identify whether the authoritative runtime is the Docker container or systemd service; record the running image/commit without exposing secrets.
- [x] 6.4 Push the verified implementation and OpenSpec change to the authoritative remote branch.
- [ ] 6.5 Deploy the matching commit/image to the verified production runtime, restart only the digest service, and confirm `/health`, scheduler state, and one controlled execution/log.
- [x] 6.6 Confirm the next scheduled email path and report any external blocker if SSH, API credentials, or SMTP verification prevents end-to-end confirmation.

> Production blocker (2026-07-15): `icode.baidu.com` resolves to private address `10.11.81.103`; TCP/22 times out from the current environment before authentication. Runtime identity, restart, scheduler, SMTP, and next-email checks require access to the corresponding private network/VPN.
