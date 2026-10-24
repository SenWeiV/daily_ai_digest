# Prioritize Trending Social Proof

## Why

The current GitHub pipeline gives recently-created and recently-pushed Repository Search channels equal or greater influence than GitHub Trending, and it treats repository completeness as the main evidence of value. The desired digest should instead surface research-relevant projects that GitHub users have already validated through rapid recent Star growth and active Issue/PR conversation, with Trending as the primary discovery source.

## What Changes

- Make GitHub Trending the primary GitHub discovery channel and remove recently-created repository discovery.
- Allow each Trending request up to 120 seconds and make at most 10 total attempts across direct, proxy, and mirror access methods; success stops retries immediately.
- Use narrow, recently-pushed Repository Search only as a bounded fallback when qualified Trending projects cannot fill the target count.
- Capture explicit social-proof metadata: Trending period/rank, recent Stars and velocity, total Stars, forks, watchers, open issues, and up to 100 Issue/PR comments from the previous 14 days.
- Replace README-first GitHub grading with relevance-plus-social-proof A/B/C rules. Total Stars have no admission floor and are used only in deterministic ordering.
- Rank GitHub projects without a fitted score: grade, Trending source, recent-Star velocity, recent comments, total Stars, repository activity, supporting implementation evidence, recency, and stable key.
- Persist and present the new metrics with backward-compatible defaults and correct daily/weekly/monthly labels.
- Keep arXiv retrieval/grading, YouTube behavior, cross-source deduplication, dynamic 10-24 selection, and post-selection model analysis unchanged.

## Capabilities

### New Capabilities

- `github-trending-discovery`: Trending-first retrieval, retry behavior, bounded popular-active fallback, and source failure isolation.
- `github-social-proof-selection`: Social-proof metadata, explicit quality gates, deterministic ordering, persistence, and presentation.

### Modified Capabilities

None. This follow-up introduces replacement GitHub capabilities while preserving the completed arXiv and combined digest contracts.

## Impact

- Backend: `github_agent.py`, `content_profile.py`, `content_selector.py`, schemas, configuration, email rendering, and persistence-compatible JSON payloads.
- Frontend: GitHub types and project list/detail presentation.
- Operations: environment templates, Docker Compose, deployment documentation, runtime verification, and production backend rollout.
- Tests: Trending retries/fallback, no-created-query guarantees, bounded comment collection, social-proof grading/ranking, legacy deserialization, email escaping, and unchanged arXiv/YouTube orchestration.
