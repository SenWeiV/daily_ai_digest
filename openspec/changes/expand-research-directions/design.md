## Context

`backend/app/content_profile.py` defines four frozen `ResearchProfile` dataclasses, each with a `domain_terms` tuple and a `content_terms` tuple. `matching_profiles()` returns a profile only when the candidate's searchable text hits at least one term from each tuple. Everything that matches nothing is graded C and dropped, so the profile set is the digest's topical boundary — not a ranking hint.

Four areas the reader now follows fall outside that boundary entirely. LeRobot does not contain `vision-language`; a 3D Gaussian Splatting renderer does not contain `benchmark` in the sense `data-evaluation` means; an MCP server collection does not contain the agent-research vocabulary `agentic` uses. These fail the gate on vocabulary, not on quality, which is why widening the existing four would be the wrong repair: `multimodal` would have to absorb robotics and `agentic` would have to absorb developer tooling, and both would stop meaning anything specific.

Two facts about the surrounding machinery shape the design:

- `_coverage_order()` in `content_selector.py` prefers items that add a new source or a new research topic. It reads `research_topics`, which is populated from `matching_profiles()`. Doubling the profile count therefore changes tie-breaking behavior with no code change at all.
- The selector takes every A-grade item up to `max_items=24` before touching B. More qualifying profiles means more A items, so runs that land near 10 today can land near 24. That is a volume change the proposal calls out as BREAKING for volume, and this design has to decide whether it is intended.

The two previously-completed changes (`expand-research-discovery`, `prioritize-trending-social-proof`) have been archived, so `openspec/specs/` now holds the canonical baselines this change modifies: `research-content-discovery` and `digest-quality-selection`. The MODIFIED deltas here target those folder names and quote each modified requirement in full, matching the canonical requirement headers exactly.

## Goals / Non-Goals

**Goals:**

- Make Physical AI, Spatial AI, full-stack skill/MCP, and AI creative/marketing content reachable by the existing two-signal gate.
- Keep each added domain vocabulary discriminative enough that one domain hit plus one content hit means genuine relevance.
- Assign every ambiguous term to exactly one profile, deliberately, and record why.
- Decide and record the intended digest volume now that more content qualifies.
- Keep one topic from occupying the whole digest when A-grade items exceed 24.

**Non-Goals:**

- No change to the A/B/C evidence rules or the social-proof gates. An added-profile candidate clears the same bar.
- No change to Trending-first discovery, to the selector's rank ordering, to YouTube, or to the email template.
- No new content sources. `cs.RO` is a category added to an existing source.
- No per-topic quota or admission threshold. Breadth is a trimming rule at the ceiling, nothing more.
- No prompt or analyzer changes. The added profiles feed the same analysis path.

## Decisions

**Four separate profiles, not four extensions of the existing ones.** The vocabularies genuinely do not overlap, and a profile name is what appears in `research_topics` and drives coverage ordering. Folding robotics into `multimodal` would make the coverage signal lie about what a digest covers. Alternative considered: one combined `applied-engineering` profile for skill/MCP plus creative/marketing, since both are developer-facing rather than research. Rejected because their content signals share nothing — `mcp integration` and `comfyui workflow` have no reason to sit in one tuple, and coverage ordering would treat an MCP server and a video model as the same topic.

**Domain vocabularies are qualified phrases only.** The spec bans a specific list of single words from every domain vocabulary: `robot`, `3d`, `video`, `animation`, `marketing`, `scene`, `simulation`, `control`, `content`, `seo`, `api`, `fullstack`, `react`, `nextjs`, `vue`, `tailwind`, `node`, `diffusion`, `transformer`. Each of these appears in a large fraction of GitHub, and the gate needs only one domain hit, so a single broad word plus a near-universal content word like `implementation` would admit almost anything. The concrete failure this prevents: `video` plus `api` would match every video player wrapper on GitHub. Where the concept is genuinely needed the qualified form carries it — `robot simulation` rather than `simulation`, `video diffusion` rather than `diffusion`.

**Every ambiguous term gets exactly one home, with one deliberate exception.** Five collisions were identified and resolved:

| Term | Assigned to | Why, and what the other profile uses instead |
| --- | --- | --- |
| `world model` | `physical-ai` | The current literature uses it for learned environments that train policies. `spatial-ai` uses `generative 3d` and `3d scene generation` for the scene-synthesis sense. |
| `spatial reasoning` | `multimodal` (unchanged) | It denotes a VLM evaluation capability, not reconstruction. `spatial-ai` uses `spatial intelligence`. |
| bare `mcp` | `agentic` (unchanged) | Already there. `fullstack-skill-mcp` uses `mcp server` and `model context protocol`, which are what developer-tooling repositories actually say. |
| `video generation` | `creative-marketing` | `multimodal` keeps `video-language`, which is the understanding side rather than the generation side. |
| `remotion` | both `fullstack-skill-mcp` and `creative-marketing` | Genuinely both a React developer tool and a video-render tool. This is the single permitted duplication and the spec says so explicitly, so it reads as a decision rather than an oversight. |

Duplication is otherwise banned because a term in two profiles inflates `research_topics` for one item, and `_coverage_order()` would then treat that item as covering two areas it does not really span.

**Multi-topic items must not gain rank from topic count.** This follows from the point above. The spec adds a scenario fixing it, because the current `_coverage_order()` rewards new-topic coverage and a term duplicated across profiles would quietly exploit that. No code change is expected — the requirement exists so a test pins the behavior.

**Intended volume: 10 is a floor, 24 is the ceiling, and larger digests are the intended outcome.** The proposal flagged this as needing a decision. The decision is to leave `target_items=10` and `max_items=24` alone and accept that runs will trend larger. The reader asked for four more areas of coverage; a digest that stayed at 10 items would be silently dropping the new areas to preserve a number that was never the point. Alternative considered: raise `target_items` to keep the ratio, or add a per-topic cap of two or three items. Both rejected — the first changes nothing that matters since the target is only a floor, and the second is exactly the kind of quota the project has avoided, and it would drop an A-grade item in favor of nothing.

**Breadth-first round robin when A-grade items exceed the maximum.** At the ceiling, admit one item per represented topic before a second from any topic, then repeat, with the existing deterministic ordering deciding within each topic. This is a trimming rule and it is inert below 24 items. It defends against one real scenario: a week when robotics is unusually active producing a digest that is 24 robotics items and nothing else. Alternative considered: rely on `_coverage_order()` as-is. Rejected because coverage ordering is a tie-breaker among otherwise-equal items, not a guarantee, so it cannot promise breadth at the ceiling.

**`cs.RO` is added; nothing else is.** Robotics and VLA papers are not retrievable at all without it. `cs.CV` already covers spatial reconstruction and video generation, so the other three profiles need no new category. Adding categories speculatively costs API calls every run for content no profile can match.

**Fallback queries stay narrow and stay a fallback.** Each added query pairs a qualified domain phrase with a content term, matching the existing convention in `DEFAULT_SEARCH_QUERIES`. Trending remains primary. The spec makes both constraints checkable so a later edit cannot quietly add a bare-word query.

## Vocabulary tables

These are the concrete term sets the spec requires. Recorded here so implementation is transcription rather than invention.

**`physical-ai`**

- Domain: `physical ai`, `embodied ai`, `embodied intelligence`, `embodied agent`, `humanoid robot`, `robot learning`, `robot manipulation`, `dexterous manipulation`, `bimanual manipulation`, `legged robot`, `locomotion`, `whole-body control`, `vla`, `vision-language-action`, `robot foundation model`, `sim-to-real`, `sim2real`, `robot simulation`, `isaac lab`, `gr00t`, `world model`, `lerobot`, `openvla`, `smolvla`, `genesis physics`
- Content: `vla model`, `robot policy`, `imitation learning`, `diffusion policy`, `flow matching policy`, `embodied benchmark`, `robot dataset`, `teleoperation`, `action chunking`, `transformer policy`, `benchmark`, `dataset`, `implementation`, `paper`

**`spatial-ai`**

- Domain: `spatial intelligence`, `3d gaussian splatting`, `3dgs`, `gaussian splatting`, `slam`, `visual slam`, `nerf`, `neural radiance field`, `novel view synthesis`, `neural rendering`, `3d reconstruction`, `scene reconstruction`, `feed-forward reconstruction`, `4d reconstruction`, `generative 3d`, `3d scene generation`
- Content: `gaussian splat`, `point cloud`, `camera pose estimation`, `monocular depth`, `photogrammetry`, `implicit representation`, `multi-view stereo`, `semantic 3d`, `benchmark`, `dataset`, `implementation`, `paper`
- NeRF terms are kept because they still appear as comparison baselines, but the spec forbids treating them as evidence of current work on their own.

**`fullstack-skill-mcp`**

- Domain: `mcp server`, `model context protocol`, `mcp registry`, `mcp client`, `agent skill`, `claude code skill`, `skill.md`, `gsap`, `framer motion`, `motion one`, `anime.js`, `lenis`, `rive`, `remotion`, `scrolltrigger`, `view transitions`, `server components`, `edge runtime`
- Content: `mcp integration`, `tool calling`, `web animation`, `react animation`, `spring animation`, `keyframe animation`, `component library`, `design system`, `monorepo`, `api gateway`, `orm`, `implementation`, `framework`

**`creative-marketing`**

- Domain: `video generation`, `text-to-video`, `image-to-video`, `video diffusion`, `wan video`, `hunyuan video`, `ltx video`, `kling`, `runway gen`, `comfyui`, `remotion`, `manim`, `motion canvas`, `motion graphics`, `ai marketing`, `marketing automation`, `social media automation`, `generative engine optimization`, `programmatic video`
- Content: `comfyui workflow`, `video model`, `caption generation`, `content calendar`, `ad generation`, `render pipeline`, `template`, `implementation`, `framework`, `api`

`sora` is deliberately absent. Its API is closing in 2026-09, so a vocabulary entry for it would decay into noise.

## Risks / Trade-offs

- **A domain phrase turns out to be broader in practice than it reads** — for example `locomotion` catching game-engine character controllers, or `slam` catching unrelated acronym uses. Mitigated by the two-signal gate and by tests that assert named unrelated repositories do not match. If a term proves noisy in production the fix is removing that one term, not loosening the structure.
- **Digest volume roughly doubles and the email becomes long enough to be skimmed instead of read** → This is the accepted consequence of the volume decision, not an accident. The 24-item ceiling already bounds it. If the email proves unreadable at 24 items that is a presentation change, and grouping by topic in the template is the natural next step — not a smaller ceiling.
- **Per-item LLM cost rises with candidate volume** → Real: more qualifying candidates means more analysis calls per run. The DeepSeek switch lowers per-call cost, which partly absorbs it. The cost is bounded by `max_items`, since deep analysis runs only on selected items.
- **`_coverage_order()` behaves differently with eight topics and nobody notices** → No code changes, so no test would fail. The spec adds explicit determinism and multi-topic scenarios so tests pin the behavior rather than inferring it.
- **`cs.RO` adds volume to arXiv retrieval, much of it classical robotics with no learning content** → The profile gate rejects it. The cost is retrieval bandwidth, not digest quality.
- **The breadth round-robin admits a weaker A item over a stronger one at the ceiling** → Accepted deliberately. Both are A-grade, and one item from a thin topic is worth more to the reader than the 25th item from a crowded one.

## Open Questions

- Should the email template group items by research topic once digests routinely run past 15 items? Not blocking; a presentation change, separate from this one.
