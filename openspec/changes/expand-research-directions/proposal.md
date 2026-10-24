## Why

The digest currently recognizes four research profiles: `multimodal`, `data-evaluation`, `agentic`, and `principles-methodology`. Anything outside those is graded C and dropped, so four areas the reader now follows never appear regardless of how strong their social proof is: Physical AI (embodied/robotics, including both application and architecture layers), Spatial AI (spatial intelligence, 3D reconstruction, spatial agents), full-stack engineering skills and MCP servers (including frontend motion and backend architecture), and AI creative/marketing tooling (video generation, programmatic video, marketing automation).

These are not adjacent refinements of the existing profiles. A LeRobot or 3D Gaussian Splatting repository fails the current `multimodal` gate because its vocabulary does not overlap; an MCP server collection fails `agentic` because the domain terms there target agent research rather than developer tooling. Widening the existing profiles would blur what they mean, so the four areas need profiles of their own.

## What Changes

- Add four research profiles to `content_profile.py`: `physical-ai`, `spatial-ai`, `fullstack-skill-mcp`, `creative-marketing`.
- Extend `ARXIV_CATEGORIES` with `cs.RO` so robotics and VLA papers are retrievable at all. `cs.CV` already covers spatial reconstruction and video generation.
- Extend the GitHub fallback search queries with narrow domain-plus-content pairs for the new profiles, keeping the existing convention that a query never consists of a bare domain word.
- Resolve vocabulary collisions with the existing profiles explicitly rather than letting terms appear in several profiles by accident. `world model`, `spatial reasoning`, `mcp`, `video generation`, and `diffusion` each already have a home or are about to acquire one.
- **BREAKING** for digest volume, not for any interface: doubling the number of profiles admits more A-grade items per run. The selector takes every A item up to `MAX_ITEMS` (24) before falling back to B, so runs that currently land near the 10-item target may start landing near 24. This change must decide and record what the intended volume is.

Non-goals: no change to the A/B/C social-proof gates, to Trending-first discovery, to the selector's ordering, to YouTube behavior, or to the email template. No new content sources.

## Capabilities

### New Capabilities

- `expanded-research-profiles`: The four added profiles, their domain and content vocabularies, the collision rules that keep a term from silently matching several profiles, and the precision constraints that keep over-broad single words out of domain vocabularies.

### Modified Capabilities

- `research-content-discovery`: The arXiv category set and the GitHub fallback query set are part of this capability's requirements, and both change. The requirement that a candidate match at least one profile using both a domain and a content signal is unchanged; what changes is the set of profiles that exist to be matched.
- `digest-quality-selection`: The dynamic 10-to-24 selection rule is unchanged as a rule, but its practical output shifts once more profiles qualify content. The requirement needs to state what happens when A-grade items exceed the target across a wider topic space, and how topic coverage is balanced so one popular area cannot occupy the whole digest.

## Impact

- Backend: `app/content_profile.py` (four new profiles), `app/config.py` (arXiv categories default), `app/agents/github_agent.py` (`DEFAULT_SEARCH_QUERIES`).
- Configuration: `backend/.env.example`, `.env.example.docker`, `docker-compose.yml` arXiv category defaults.
- Selection behavior: `research_topics` feeds `_coverage_order`, so a wider topic space changes which items win coverage ties. No code change, but the effect is real and needs verification.
- Tests: per-profile positive matches against named real repositories, negative matches for over-broad terms, collision rules, arXiv category wiring, and a selection test covering the case where A-grade items span more topics than the target count.
- Cost: more qualifying candidates means more per-item LLM analysis calls per run. Interacts with the DeepSeek switch, which lowers per-call cost.
