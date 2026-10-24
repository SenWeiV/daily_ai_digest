## ADDED Requirements

### Requirement: Physical AI content is discoverable

The system MUST define a `physical-ai` research profile covering embodied and robotic AI at both the application layer (humanoid robots, manipulation, locomotion, autonomous driving, industrial automation) and the architecture layer (vision-language-action models, world models used as training environments, robot foundation models).

Domain vocabulary MUST include the terms that the field actually uses in 2026: `physical ai`, `embodied ai`, `embodied intelligence`, `embodied agent`, `humanoid robot`, `robot learning`, `robot manipulation`, `dexterous manipulation`, `bimanual manipulation`, `legged robot`, `locomotion`, `whole-body control`, `vla`, `vision-language-action`, `robot foundation model`, `sim-to-real`, `sim2real`, `robot simulation`, `isaac lab`, `gr00t`, `world model`, `lerobot`, `openvla`, `smolvla`, `genesis physics`.

Content vocabulary MUST include implementation and evaluation signals: `vla model`, `robot policy`, `imitation learning`, `diffusion policy`, `flow matching policy`, `embodied benchmark`, `robot dataset`, `teleoperation`, `action chunking`, `transformer policy`, `benchmark`, `dataset`, `implementation`, `paper`.

#### Scenario: A VLA implementation repository matches

- **WHEN** a repository's searchable metadata contains `vision-language-action` and `robot policy`
- **THEN** it MUST match the `physical-ai` profile

#### Scenario: A robot learning framework matches

- **WHEN** a repository's searchable metadata contains `lerobot` and `robot dataset`
- **THEN** it MUST match the `physical-ai` profile

#### Scenario: A bare mechanical-robotics repository does not match

- **WHEN** a repository describes an Arduino-driven hobby robot arm with no learning, policy, or model vocabulary
- **THEN** it MUST NOT match the `physical-ai` profile

### Requirement: Spatial AI content is discoverable

The system MUST define a `spatial-ai` research profile covering spatial intelligence, 3D scene reconstruction and generation, and spatial agents or model architectures.

Domain vocabulary MUST include `spatial intelligence`, `3d gaussian splatting`, `3dgs`, `gaussian splatting`, `slam`, `visual slam`, `nerf`, `neural radiance field`, `novel view synthesis`, `neural rendering`, `3d reconstruction`, `scene reconstruction`, `feed-forward reconstruction`, `4d reconstruction`, `generative 3d`, `3d scene generation`.

Content vocabulary MUST include `gaussian splat`, `point cloud`, `camera pose estimation`, `monocular depth`, `photogrammetry`, `implicit representation`, `multi-view stereo`, `semantic 3d`, `benchmark`, `dataset`, `implementation`, `paper`.

NeRF vocabulary MUST be retained because it still appears as a comparison baseline, but MUST NOT be treated as evidence that a candidate represents current work on its own.

#### Scenario: A Gaussian Splatting renderer matches

- **WHEN** a repository's searchable metadata contains `3d gaussian splatting` and `point cloud`
- **THEN** it MUST match the `spatial-ai` profile

#### Scenario: A feed-forward reconstruction model matches

- **WHEN** a repository's searchable metadata contains `feed-forward reconstruction` and `camera pose estimation`
- **THEN** it MUST match the `spatial-ai` profile

#### Scenario: An AR/VR application does not match on spatial computing alone

- **WHEN** a repository describes a headset UI toolkit and contains `spatial computing` but no reconstruction, rendering, or scene vocabulary
- **THEN** it MUST NOT match the `spatial-ai` profile

### Requirement: Full-stack skill and MCP content is discoverable

The system MUST define a `fullstack-skill-mcp` research profile covering MCP servers, agent skill packages, frontend motion libraries, and backend architecture patterns aimed at developers rather than at research.

Domain vocabulary MUST include `mcp server`, `model context protocol`, `mcp registry`, `mcp client`, `agent skill`, `claude code skill`, `skill.md`, `gsap`, `framer motion`, `motion one`, `anime.js`, `lenis`, `rive`, `remotion`, `scrolltrigger`, `view transitions`, `server components`, `edge runtime`.

Content vocabulary MUST include `mcp integration`, `tool calling`, `web animation`, `react animation`, `spring animation`, `keyframe animation`, `component library`, `design system`, `monorepo`, `api gateway`, `orm`, `implementation`, `framework`.

Domain vocabulary MUST NOT include bare framework names that dominate general web development, specifically `react`, `nextjs`, `vue`, `tailwind`, `node`, `api`, or `fullstack`. These MAY appear as content signals only.

#### Scenario: An MCP server collection matches

- **WHEN** a repository's searchable metadata contains `model context protocol` and `mcp integration`
- **THEN** it MUST match the `fullstack-skill-mcp` profile

#### Scenario: A motion library matches

- **WHEN** a repository's searchable metadata contains `gsap` and `web animation`
- **THEN** it MUST match the `fullstack-skill-mcp` profile

#### Scenario: A generic web starter template does not match

- **WHEN** a repository is a Next.js and Tailwind starter with no motion, MCP, or skill vocabulary
- **THEN** it MUST NOT match the `fullstack-skill-mcp` profile

### Requirement: AI creative and marketing tooling is discoverable

The system MUST define a `creative-marketing` research profile covering AI video generation, programmatic video and animation, and marketing content automation.

Domain vocabulary MUST include `video generation`, `text-to-video`, `image-to-video`, `video diffusion`, `wan video`, `hunyuan video`, `ltx video`, `kling`, `runway gen`, `comfyui`, `remotion`, `manim`, `motion canvas`, `motion graphics`, `ai marketing`, `marketing automation`, `social media automation`, `generative engine optimization`, `programmatic video`.

Content vocabulary MUST include `comfyui workflow`, `video model`, `caption generation`, `content calendar`, `ad generation`, `render pipeline`, `template`, `implementation`, `framework`, `api`.

Domain vocabulary MUST NOT include the bare words `video`, `animation`, `marketing`, `content`, or `seo`.

Vocabulary for retired products MUST NOT be added. `sora` in particular MUST NOT be used as a domain term.

#### Scenario: An open-weight video model matches

- **WHEN** a repository's searchable metadata contains `text-to-video` and `video model`
- **THEN** it MUST match the `creative-marketing` profile

#### Scenario: A programmatic video framework matches

- **WHEN** a repository's searchable metadata contains `remotion` and `render pipeline`
- **THEN** it MUST match the `creative-marketing` profile

#### Scenario: A video player library does not match

- **WHEN** a repository is an HTML5 video playback component containing the word `video` but no generation, diffusion, or programmatic-render vocabulary
- **THEN** it MUST NOT match the `creative-marketing` profile

### Requirement: Each vocabulary term belongs to exactly one profile

A term that could plausibly describe more than one profile MUST be assigned to the single profile where it is most discriminative, and MUST NOT be duplicated across profiles. Assignment MUST follow these resolutions:

- `world model` belongs to `physical-ai`. `spatial-ai` MUST use `generative 3d` and `3d scene generation` for the scene-generation sense.
- `spatial reasoning` remains in `multimodal`, where it denotes a vision-language evaluation capability. `spatial-ai` MUST use `spatial intelligence`.
- bare `mcp` remains in `agentic`. `fullstack-skill-mcp` MUST use `mcp server` and `model context protocol`.
- `video generation` belongs to `creative-marketing`. `multimodal` retains `video-language`.
- `remotion` appears in both `fullstack-skill-mcp` and `creative-marketing` because it is genuinely both a developer tool and a video tool. This is the single permitted exception and MUST be the only term present in two profiles.

#### Scenario: A world-model paper is tagged once

- **WHEN** a paper's metadata contains `world model` and a robotics content signal
- **THEN** `physical-ai` MUST appear in its research topics
- **AND** `spatial-ai` MUST NOT be added on the strength of `world model` alone

#### Scenario: A VLM spatial-reasoning benchmark is tagged as multimodal

- **WHEN** a repository's metadata contains `spatial reasoning` and `benchmark` but no reconstruction or rendering vocabulary
- **THEN** `multimodal` MUST appear in its research topics
- **AND** `spatial-ai` MUST NOT

#### Scenario: Remotion is tagged twice by design

- **WHEN** a repository's metadata contains `remotion` and satisfies the content vocabulary of both profiles
- **THEN** both `fullstack-skill-mcp` and `creative-marketing` MAY appear in its research topics

### Requirement: Domain vocabularies exclude over-broad single words

A domain term MUST be discriminative enough that its presence, combined with any content signal, indicates genuine topical relevance. Single words that occur across large portions of GitHub MUST NOT be used as domain terms. The following MUST NOT appear in any domain vocabulary: `robot`, `3d`, `video`, `animation`, `marketing`, `scene`, `simulation`, `control`, `content`, `seo`, `api`, `fullstack`, `react`, `nextjs`, `vue`, `tailwind`, `node`, `diffusion`, `transformer`.

Where the underlying concept is needed, a qualified phrase MUST be used instead.

#### Scenario: An unrelated repository containing a broad word is rejected

- **WHEN** a repository description contains `simulation` and `implementation` but no qualified domain phrase from any profile
- **THEN** it MUST NOT match any of the four added profiles

#### Scenario: The qualified phrase still matches

- **WHEN** a repository description contains `robot simulation` and `implementation`
- **THEN** it MUST match the `physical-ai` profile
