# Expand Research Discovery

## Why

The current digest discovers GitHub projects primarily through Trending, broad string matching, today's Star growth, and a hard Top 10 slice. This misses recently created but valuable AI research and engineering projects, evaluation assets, datasets, and paper implementations. The digest also has no first-class paper source, so important arXiv work is absent or delayed until a related repository becomes popular.

The next daily run needs to surface the user's current research interests without destabilizing the existing YouTube workflow: multimodal models, data and evaluation, agentic applications, and the principles and methods behind them.

## What Changes

- Upgrade GitHub discovery from a single Trending/filter path to three complementary candidate paths:
  - existing Trending projects;
  - recently created repositories searched by narrow topic queries, with value evidence required;
  - recently updated research repositories, including repositories that explicitly link to papers.
- Prioritize newly created GitHub projects that demonstrate substantive value through README, topics, implementation, tests, experiments, benchmark, dataset, or other concrete evidence.
- Add arXiv as an independent paper discovery source for relevant computer science categories and normalize paper versions/categories during deduplication.
- Link a paper and repository only when an explicit arXiv/GitHub relationship is present; use title similarity only as a non-merging hint.
- Replace the source-specific hard Top 10 behavior with a shared A/B/C quality selection layer:
  - target 10 items;
  - publish all qualifying A items;
  - use B items only to fill to 10;
  - never use C items as filler;
  - allow up to 24 items when many A items qualify.
- Keep YouTube discovery, analysis, quantity, and output behavior unchanged.
- Add arXiv data to persisted digest records, API responses, email rendering, frontend types/views, and historical digest display while preserving old SQLite records.
- Add tests for discovery relevance, new-project value evidence, cross-channel deduplication, paper/repository linking, quality selection, persistence compatibility, and YouTube regression behavior.
- Document and verify the production deployment update so the next scheduled email run uses the new pipeline.

## Capabilities

### New Capabilities

- `research-content-discovery` - GitHub Trending/Search and arXiv candidate discovery, relevance, value evidence, deduplication, and explicit cross-source linking.
- `digest-quality-selection` - A/B/C quality classification and target/max dynamic digest selection shared by GitHub and arXiv.
- `arxiv-digest-source` - arXiv retrieval, normalization, paper metadata, and paper-specific analysis data.

### Modified Capabilities

- None. The repository has legacy `.comate` notes but no existing standard OpenSpec capability specifications; the capabilities above establish the new contracts for this change.

## Impact

- Backend agents, schemas, persistence models, database initialization/migration, digest orchestration, analyzer prompts, email templates, API serialization, and frontend history/types.
- New configuration for arXiv and discovery/selection limits may be added with backward-compatible defaults.
- GitHub API request volume will increase through bounded, narrow search queries; candidate retrieval and deep analysis must remain separately bounded to control cost and rate limits.
- Production deployment requires updating the running backend image/container or service and verifying the scheduled job, health endpoint, and next email path without exposing secrets.
