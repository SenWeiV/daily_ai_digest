# Implementation Tasks

## 1. Contracts and configuration

- [x] 1.1 Add backward-compatible Trending period/rank, recent-Star, velocity, source, watcher, open-issue, and recent-comment fields to the GitHub item schema and frontend types.
- [x] 1.2 Replace the outer Trending timeout/new-project settings with per-attempt timeout, global attempt count, popular-active window, social window, and comment cap settings across backend config, environment templates, Compose, and deployment docs.
- [x] 1.3 Add tests for schema legacy defaults and configuration defaults.

## 2. Trending-first discovery

- [x] 2.1 Refactor Trending retrieval to use one global 10-attempt budget, a 120-second timeout per attempt, access-method cycling, first-success termination, and bounded retry delays.
- [x] 2.2 Parse and retain Trending rank, period recent Stars, period days, and recent-Star velocity with correct daily/weekly/monthly semantics.
- [x] 2.3 Remove all recently-created Repository Search queries and rename/refactor the remaining recently-pushed, Star-sorted Search as a fallback-only source.
- [x] 2.4 Run popular-active Search only when qualified Trending candidates cannot fill `TARGET_ITEMS`, while preserving Trending results if Search fails.
- [x] 2.5 Keep the total inspection pool bounded, deduplicate by numeric repository ID, and preserve explicit arXiv relations.
- [x] 2.6 Add tests for exactly 10 total attempts, 120-second request timeout wiring, access cycling, stop-on-success, no `created:`, fallback-only invocation, and source failure isolation.

## 3. Social-proof enrichment and grades

- [x] 3.1 Enrich bounded candidates with cheap total Stars, forks, watchers, and open-issue fields from the existing PyGithub repository object.
- [x] 3.2 Count Issue/PR comments from the configured 14-day window, stop at 100, and represent endpoint failure as unavailable rather than zero.
- [x] 3.3 Replace README-first GitHub grading with mandatory research relevance and explicit Trending/social-proof A/B/C gates, with no total-Star admission floor.
- [x] 3.4 Implement deterministic popularity-first ordering: grade, source, recent-Star velocity, recent comments, total Stars, repository activity, implementation evidence, recency, stable key.
- [x] 3.5 Keep fallback Search candidates at B or C because they lack observed Trending recent-Star growth.
- [x] 3.6 Add tests for bounded comments, API failure isolation, unrelated popular C, small fast-rising A, mature fallback B, README-only non-A, and lexicographic ordering.

## 4. Persistence and presentation

- [x] 4.1 Round-trip new social-proof fields through digest JSON and verify old rows deserialize with defaults without a table migration.
- [x] 4.2 Update email GitHub rendering with escaped period-correct recent Stars, total Stars, and recent comments while preserving arXiv and YouTube sections.
- [x] 4.3 Update frontend GitHub list/detail presentation to show period-correct momentum and social proof without changing arXiv or YouTube views.
- [x] 4.4 Add persistence, email escaping/label, and frontend build/type regression coverage.

## 5. Orchestration and verification

- [x] 5.1 Confirm deep GitHub model analysis remains after shared selection and bounded by final selected GitHub count.
- [x] 5.2 Run complete backend tests, Python compile checks, frontend typecheck/build, diff checks, and strict OpenSpec validation.
- [x] 5.3 Run the repository runtime verifier with isolated fixtures and confirm GitHub/arXiv dynamic counts plus unchanged YouTube behavior.
- [x] 5.4 Stage the full diff, run an independent verifier, and resolve all actionable findings before committing.

## 6. Production rollout

- [ ] 6.1 Push the verified commits to the authoritative `origin/main` branch and confirm the frontend deployment workflow.
- [ ] 6.2 Verify the current production Docker revision/data mount, tag a rollback image, and create an SQLite backup without exposing secrets.
- [ ] 6.3 Deploy an isolated backend overlay retaining `/opt/daily_ai_digest/data`, then confirm revision, container health, database history, and scheduler state.
- [ ] 6.4 Run a no-email non-daily production digest and verify Trending retry behavior, fallback behavior, social-proof payloads, final counts, execution log type, and next daily email slot.
