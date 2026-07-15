# Design: Expand Research Discovery

## Context

The backend is a FastAPI application with APScheduler, SQLite persistence, GitHub and YouTube agents, a Gemini-compatible analyzer, email rendering, and a React frontend. The current GitHub agent scrapes Trending, filters repository name/description with a hard-coded broad keyword list, sorts by `stars_today`, and truncates to a configured Top 10. The digest service runs GitHub and YouTube collection together and persists JSON payloads in `digest_records`.

The change must support the user's research focus on multimodal models, data/evaluation, agentic applications, and the principles/methods behind them. It must preserve YouTube behavior and remain usable on the existing production deployment with old SQLite records and existing environment variables.

The highest-risk ambiguity is what “new project” means. A recently created repository is only a candidate; it must also show value evidence before it can enter the digest. Star count alone cannot establish value, particularly for new repositories and papers.

## Goals / Non-Goals

### Goals

- Discover relevant, recently created GitHub repositories through bounded, narrow Repository Search queries.
- Preserve Trending as a separate hot-project channel and add a bounded recently-updated research channel.
- Discover relevant arXiv papers from official RSS/Atom category feeds without requiring a new API key.
- Use explicit domain + content-type matching and an evidence-based A/B/C quality grade.
- Deduplicate within and across sources, and link papers to repositories only on explicit URLs/IDs.
- Select a daily digest with target 10 and maximum 24 items, without low-quality filler.
- Persist and render arXiv items while reading legacy records safely.
- Keep YouTube collection and output behavior unchanged.
- Make the scheduled production run verifiable before the next daily email.

### Non-Goals

- No change to YouTube search terms, ranking, quantity, transcript handling, or analyzer prompt.
- No user-personalized score fitting or ranking thresholds derived from that day's score distribution.
- No arbitrary title-similarity merging of papers and repositories.
- No replacement of SQLite, the scheduler, SMTP, or the existing LLM provider.
- No frontend redesign beyond exposing the new source and dynamic item count.
- No automatic deployment when the server identity or running process cannot be verified.

## Decisions

### 1. Use three GitHub candidate channels

The GitHub agent will retain Trending and add:

1. Trending candidates for current momentum.
2. Recently-created candidates using narrow `in:name,description,readme`, `created:` and `topic:` queries over the configured research profiles.
3. Recently-updated research candidates using `pushed:` and explicit paper/benchmark/dataset/tool signals.

Search windows and candidate limits are configuration values with conservative defaults. Search results are merged by numeric GitHub repository ID. The implementation must not fall back to unrelated Trending repositories when no relevant result exists.

**Value evidence for a new repository** is derived from metadata fetched for the candidate: a non-empty substantive README, relevant topics, declared language, meaningful repository contents, tests/examples, benchmark or dataset artifacts, an explicit paper link, or a concrete implementation description. A repository with only a broad keyword, empty/placeholder README, marketing copy, or no relevant artifact is C-grade and cannot be used to fill the digest.

Alternative considered: only expand the hard-coded keyword list. Rejected because it cannot discover repositories whose relevance is expressed in README/topics and does not distinguish valuable new work from keyword noise.

### 2. Add arXiv through official RSS/Atom feeds

Use `httpx` against official arXiv RSS/Atom category endpoints for `cs.AI`, `cs.CL`, `cs.CV`, `cs.LG`, and `cs.IR`, with optional `cs.HC`, `cs.RO`, and `eess.AS` when configured. Parse title, abstract, authors, categories, published/updated timestamps, DOI/links when available, and canonical arXiv URL.

Normalize an arXiv identifier by removing the version suffix for deduplication while preserving the submitted/updated timestamps and displayed version. Merge duplicate category entries by canonical ID. Extract explicit GitHub URLs from paper metadata/abstract/links and extract explicit arXiv IDs from GitHub README content. Store a relation only when an explicit URL or identifier is present.

Alternative considered: use the arXiv API for every daily request. RSS is preferred for daily bounded retrieval and no credential requirement; the API remains suitable for future historical/weekly backfills.

### 3. Introduce normalized candidate and quality-selection contracts

Create internal source-neutral candidate/quality structures rather than forcing GitHub and arXiv into the existing YouTube model. Each candidate carries source, stable key, title, URL, topic matches, evidence flags, timestamps, optional related keys, and source-specific payload.

A shared selector assigns an explicit grade:

- **A**: strongly relevant, substantive primary source, and concrete method/implementation/experiment/dataset/benchmark evidence.
- **B**: directly relevant and useful, but evidence or implementation detail is incomplete.
- **C**: broad keyword match, generic news/marketing, placeholder/empty project, duplicate, or insufficient evidence.

The selector first deduplicates, then enforces source/topic coverage, then selects all A items up to `max_items=24`; if A items are fewer than `target_items=10`, it adds B items until target. It never adds C items. When more than 24 A items qualify, deterministic tie-breakers are topic coverage, source/content-type coverage, recency, evidence completeness, and source-specific momentum. No threshold is fitted to the daily score distribution.

Alternative considered: one global numeric score sorted to Top 10. Rejected because Star/watch signals do not exist or are not comparable for papers and newly created repositories.

### 4. Preserve old persistence and API compatibility

Extend `DigestRecord` with an optional `arxiv_data` list and add an `ArxivDigestItem` schema. Persist it as a nullable JSON column using the existing SQLite initialization/migration pattern. Reads of old rows treat missing/null/invalid arXiv payload as an empty list; no historical row rewrite is required. API responses include the optional/empty arXiv list consistently, and frontend types use a backward-compatible default.

The digest service collects GitHub and arXiv in parallel, leaves YouTube invocation unchanged, runs the shared selector over GitHub/arXiv only, performs deep analysis only for selected items, persists the selected source-specific lists, and passes all three sections to email/frontend renderers.

### 5. Use source-specific analyzer prompts

Keep the existing GitHub and YouTube analysis behavior where possible. Add a paper analysis path that requests problem, method, evaluation, result, limitations, and implementation/repository links. The analyzer must receive source metadata and must not invent missing experimental results. Email and frontend show arXiv as a distinct section while retaining GitHub and YouTube sections.

### 6. Configuration and deployment

Add backward-compatible settings for arXiv category list, search windows, per-channel candidate limits, `TARGET_ITEMS=10`, and `MAX_ITEMS=24`. Environment templates and deployment documentation must include non-secret defaults. The production update procedure is: run tests/build locally, push the implementation branch to `origin/main` only after verification, identify whether the live Baidu service is the documented Docker container or systemd process, update the corresponding code/image, restart only that service, call `/health`, trigger a controlled digest if supported, and inspect execution logs. If SSH remains unavailable or the live process cannot be identified, stop before making a remote mutation and report the blocker.

## Data Flow

```text
GitHub Trending ─┐
GitHub Search ───┼─> source candidates -> cheap relevance/evidence grade
arXiv RSS ───────┘                         -> stable-key dedup
                                             -> explicit paper/repo links
                                             -> shared A/B/C selector (10 target, 24 max)
                                             -> deep source-specific analysis
YouTube (unchanged) -----------------------> existing analysis path
                                             -> persistence -> API/email/frontend
```

## Risks / Trade-offs

- GitHub Search increases API calls and may hit rate limits. Mitigate with narrow queries, per-channel caps, retry/backoff already used by the agent, and no deep analysis before selection.
- arXiv feed availability or XML shape changes can fail a source. Treat arXiv failure as an empty source with a logged execution error; GitHub/YouTube should still produce a digest.
- SQLite schema changes can break old deployments if initialization is not idempotent. Use additive nullable migration and test against a database created by the current version.
- Dynamic counts may make email length variable. Keep `max_items=24`, deterministic ordering, and a compact paper summary template.
- A value-evidence rule can exclude genuinely valuable but sparse new projects. B-grade retention and explicit evidence flags make the decision inspectable; future tuning can adjust profiles without changing the selector contract.
- The server may not be reachable or may run systemd instead of Docker. Verify before deployment and do not overwrite unknown remote state.

## Verification Plan

- Unit tests for profile matching, evidence extraction, GitHub channel deduplication, arXiv parsing/version/category deduplication, explicit relation extraction, A/B/C grading, and all target/max selection examples.
- Integration tests for digest generation with mocked GitHub, arXiv, YouTube, analyzer, SQLite, and email services; assert YouTube call inputs/outputs are unchanged.
- Compatibility test loading a legacy SQLite record without arXiv data.
- Local production-like run with scheduler disabled or a controlled manual digest, followed by API health and persisted-record checks.
- Remote smoke test after deployment: container/service status, `/health`, one controlled digest execution or execution log, and confirmation that the next scheduled job remains enabled.
