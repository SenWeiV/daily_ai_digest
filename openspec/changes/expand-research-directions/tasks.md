# Implementation Tasks

## 1. Profile definitions

- [x] 1.1 Add `physical-ai`, `spatial-ai`, `fullstack-skill-mcp`, and `creative-marketing` to `RESEARCH_PROFILES` in `backend/app/content_profile.py`, transcribing the vocabulary tables from `design.md` verbatim.
- [x] 1.2 Add a test asserting no term appears in more than one profile's `domain_terms`, with `remotion` as the single allowed exception. This test is the guard that keeps the collision resolutions from eroding.
- [x] 1.3 Add a test asserting none of the banned single words appear in any `domain_terms` tuple: `robot`, `3d`, `video`, `animation`, `marketing`, `scene`, `simulation`, `control`, `content`, `seo`, `api`, `fullstack`, `react`, `nextjs`, `vue`, `tailwind`, `node`, `diffusion`, `transformer`.
- [x] 1.4 Add positive-match tests against real repository metadata for each added profile — LeRobot, a 3D Gaussian Splatting implementation, an MCP server collection, and an open-weight video model. Use metadata copied from the actual repositories, not invented strings.
- [x] 1.5 Add negative-match tests: an Arduino hobby robot arm, an AR/VR headset UI toolkit, a Next.js + Tailwind starter, and an HTML5 video player component. Each MUST match none of the four added profiles.
- [x] 1.6 Add collision tests: `world model` plus a robotics content signal yields `physical-ai` and not `spatial-ai`; `spatial reasoning` plus `benchmark` yields `multimodal` and not `spatial-ai`.

## 2. Discovery wiring

- [x] 2.1 Add `cs.RO` to the `arxiv_categories` default in `backend/app/config.py`, keeping the existing five.
- [x] 2.2 Update the arXiv category default in `backend/.env.example`, `.env.example.docker`, and `docker-compose.yml` so all four surfaces name the same set.
- [x] 2.3 Add a test asserting the application default contains all six categories, and a test asserting the Compose default string matches the application default.
- [x] 2.4 Extend `DEFAULT_SEARCH_QUERIES` in `backend/app/agents/github_agent.py` with narrow domain-plus-content queries for the four added profiles.
- [x] 2.5 Add a test asserting every entry in `DEFAULT_SEARCH_QUERIES` contains at least two terms and that no entry consists solely of a banned single word.

## 3. Selection behavior

- [x] 3.1 Implement the breadth-first round robin in `select_research_items()` for the case where A-grade items exceed `max_items`: one item per represented topic before a second from any topic, existing deterministic ordering deciding within each topic. Leave behavior at or below the maximum untouched.
- [x] 3.2 Add a test for the 30-candidate case where 25 share one topic and five other topics have one each: all five thin-topic items MUST be selected, and the remainder filled deterministically.
- [x] 3.3 Add a test asserting the trimming rule is inert below the maximum — 12 qualifying items with 11 sharing a topic MUST all be selected.
- [x] 3.4 Add a test asserting the over-maximum selection is identical across two runs with the same input.
- [x] 3.5 Add a test asserting two A-grade items with equal evidence order the same regardless of how many research topics each carries.
- [x] 3.6 Confirm by reading `_coverage_order()` that no grading or selection rule branches on which profile matched, and add a test asserting an added-profile candidate with no evidence is graded C exactly as an existing-profile equivalent would be.

## 4. Verification

- [x] 4.1 Run the backend test suite and a Python compile check.
- [ ] 4.2 Run one `force=true, send_email=false` digest against the new profile set. Record the item count, the grade distribution, and the topic distribution across selected items.
- [ ] 4.3 Read the selected items and report how many are genuinely relevant to the four added areas versus admitted by an over-broad term. If any term is admitting noise, remove that term and rerun rather than adjusting the gate.
- [ ] 4.4 Compare the item count against the most recent pre-change run and report the volume shift against the recorded intent — 10 as a floor, 24 as the ceiling, larger digests expected.

## Notes

Task 4.3 is the real test of this change. The vocabulary tables are reasoned but unproven against live GitHub data; a term that reads as discriminative can still be common in practice. The response to noise is removing the specific term, never loosening the two-signal gate or adding a per-topic quota.

Task 3.1 is the only behavioral code change outside `content_profile.py`. Everything else is vocabulary and configuration. The profile set feeds `_coverage_order()` through `research_topics`, so tie-breaking shifts even where no code changes — tasks 3.4 and 3.5 exist to pin that rather than discover it in production.
