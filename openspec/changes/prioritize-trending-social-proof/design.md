# Design: Prioritize Trending Social Proof

## Context

The GitHub agent currently runs Trending and Repository Search together, including a recently-created channel, then grades repositories mainly from README and implementation evidence. Production showed that Trending can be slow from the Baidu host, so a two-minute outer timeout was added; that makes Search dominate even though the desired signal is GitHub's own recent-Star momentum. The revised policy requires up to 10 two-minute Trending attempts, removes newly-created discovery, and defines value through research relevance plus visible social proof.

PyGithub already supplies total Stars, forks, watchers, and open issue counts from the repository representation. It has a bounded `get_issues_comments(since=...)` path for recent Issue/PR comments. There is no cheap exact recent-Star API for arbitrary repositories, so Trending's period Star count is the authoritative momentum signal. GitHub Discussions would require separate GraphQL/REST integration and is outside the selected scope.

## Goals / Non-Goals

### Goals

- Make Trending the primary and normally sufficient GitHub source.
- Honor 120 seconds per attempt and 10 total attempts without multiplying the retry budget by access method.
- Remove recently-created repository discovery.
- Use recent Stars and bounded recent Issue/PR comments as primary value evidence.
- Preserve useful fallback behavior, API budgets, deterministic selection, old JSON rows, and the existing arXiv/YouTube paths.

### Non-Goals

- Enumerating stargazers or maintaining an exact Star-event history.
- Querying GitHub Discussions GraphQL.
- Introducing a fitted popularity score or a total-Star admission floor.
- Changing arXiv grading, YouTube retrieval, digest count rules, or the scheduler start time.

## Decisions

### Decision 1: One global Trending retry budget

`fetch_trending_repos()` will own one attempt loop with at most 10 attempts. Each attempt selects the next available direct/proxy/mirror URL, applies a 120-second HTTP timeout, and stops on the first valid parsed result. Retry delay is short and capped.

Alternative considered: retain a 120-second outer `asyncio.wait_for`. Rejected because it discards Trending after one attempt and contradicts the requested retry semantics.

Alternative considered: 10 retries for every fallback URL. Rejected because multiple access methods could expand worst-case duration far beyond 20 minutes.

### Decision 2: Trending first, pushed Search only as fallback

The agent will enrich and grade Trending candidates first. Only when fewer than `TARGET_ITEMS` qualified Trending repositories remain will it run narrow Repository Search with `pushed:>=cutoff`, sorted by total Stars. It will never use `created:`. Fallback results can fill missing B-grade positions but cannot displace qualified Trending A-grade projects.

Alternative considered: Trending only. Rejected because all 10 attempts can fail on the production network and an empty GitHub section is avoidable.

### Decision 3: Trending provides recent-Star truth

The parser will retain period, rank, period Star count, and a comparable velocity (`recent_stars / 1`, `/ 7`, or `/ 30`). `stars_today` remains a compatibility field, but new presentation uses explicit period fields.

Alternative considered: `get_stargazers_with_dates()`. Rejected because mature repositories may require scanning many pages and exhaust the API budget.

Alternative considered: derive deltas from prior digest rows. Rejected as the primary metric because repositories are not guaranteed to appear in consecutive snapshots and reruns overwrite a date/type key.

### Decision 4: Bounded Issue/PR comment activity

For the bounded inspection pool only, call `repo.get_issues_comments(since=now-14d)` and stop after 100 comments. Cheap repository fields add watchers, open issues, and forks. A failure produces `None` for recent comments, not zero, so API availability is not treated as evidence of inactivity.

Alternative considered: GitHub Discussions. Rejected because PyGithub 2.2 has no repository Discussions wrapper and additional GraphQL permissions/cost are not justified.

### Decision 5: Explicit social-proof grades and lexicographic ordering

Relevance remains mandatory. GitHub grades are evidence gates:

- A: relevant Trending item, observed recent-Star growth, and strong conversation evidence (default at least five recent Issue/PR comments). If the comment endpoint is unavailable, multiple cheap activity signals can establish social proof.
- B: relevant Trending item with recent-Star growth but weak/unavailable conversation evidence, or a socially proven popular-active fallback without a Trending gain.
- C: unrelated, keyword-only, no observable popularity/social proof, duplicate, placeholder, or marketing content.

Total Stars have no hard minimum. Ordering is lexicographic rather than weighted: grade, Trending source, recent-Star velocity, recent comments, total Stars, forks/watchers/open issues, supporting implementation evidence, recency, stable key.

### Decision 6: JSON-compatible schema evolution

New fields use defaults and remain inside the existing `github_data` JSON. No table rebuild or destructive migration is required. Old rows deserialize with zero/empty/nullable social metrics.

## Risks / Trade-offs

- [Ten failed attempts can delay email by roughly 20 minutes] → The scheduler invokes generation and email in the same coroutine, so delivery is delayed rather than skipped; `max_instances=1` and `DigestService.is_running` prevent overlap. Runtime verification will report actual duration.
- [Issue comments require paginated API calls] → Enrich no more than 24 candidates, cap at 100 comments, and isolate failures per repository.
- [Open issue count includes pull requests] → Treat it as a secondary activity signal, not a literal discussion count.
- [Trending HTML can change] → Keep parser fixtures and explicit period/rank tests; invalid parsed pages count as failed attempts.
- [No total-Star floor can admit a small but rapidly rising project] → This is intentional; recent momentum and conversation rank it, while total Stars remain an ordering signal.
- [Fallback Search lacks exact recent-Star gain] → Restrict it to filling missing B-grade positions after Trending.

## Migration Plan

1. Add backward-compatible schema/config fields and update examples.
2. Refactor retry and fallback logic behind unit tests.
3. Add social enrichment and deterministic grades/order.
4. Update email/frontend presentation and verify old records.
5. Run local runtime verification and independent staged review.
6. Back up production SQLite and tag the current image.
7. Deploy an isolated backend overlay retaining `/opt/daily_ai_digest/data`.
8. Run a no-email non-daily execution and verify health, retry logs, metrics, scheduler, and next daily slot.

Rollback uses the existing tagged image and pre-deploy SQLite backup; no schema rollback is required for JSON-only fields.

## Open Questions

None. The retry semantics, Issue/PR comment metric, and absence of a total-Star floor were explicitly selected.
