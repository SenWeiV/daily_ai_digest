## ADDED Requirements

### Requirement: Three model roles are configured independently

The system MUST separate three distinct model roles and MUST allow each to be configured with its own model identifier, base URL, and credential:

- a **text analysis role**, used for per-item analysis, period summaries, and platform copy generation
- a **visual inspection role**, used only to inspect rendered images
- an **image generation role**, used only to produce decorative background imagery

The default text analysis model MUST be DeepSeek V4 Flash. The default visual inspection model MUST be Kimi K3. The default image generation model MUST be a Seedream model that supports consistent multi-image sets.

No role may fall back to another role's model. A text-only model MUST NOT be sent an image, the visual role MUST NOT be used for text analysis, and the generation role MUST NOT be used for inspection.

#### Scenario: Roles use different models by default

- **WHEN** no override is configured
- **THEN** text analysis requests MUST carry the DeepSeek model identifier
- **AND** visual inspection requests MUST carry the Kimi K3 model identifier
- **AND** generation requests MUST carry the configured Seedream model identifier

#### Scenario: Each role has its own credential and host

- **WHEN** the configuration is read
- **THEN** each role MUST resolve its own base URL and credential independently of the others

#### Scenario: No cross-role fallback

- **WHEN** the visual inspection model is unavailable
- **THEN** the system MUST NOT send images to the text analysis model
- **AND** MUST NOT treat a generation-role response as an inspection verdict

#### Scenario: Text analysis is never charged to the vision model

- **WHEN** per-item analysis runs
- **THEN** the request MUST target the text analysis model

### Requirement: The visual inspection endpoint targets a mainland-reachable host

The deployment host is in mainland China without a VPN. The visual inspection role's default base URL MUST be a host verified reachable from mainland China. For Kimi this means the `api.moonshot.cn` endpoint rather than the `api.moonshot.ai` endpoint, which was measured as unreliable from a mainland network.

Documentation MUST state that the two Kimi endpoints are separate platforms with separate accounts, separate credentials, and separate currencies, so an operator does not assume one key works on both.

#### Scenario: Default host is the mainland endpoint

- **WHEN** no base URL override is configured for the visual role
- **THEN** the resolved host MUST be the mainland Kimi endpoint

#### Scenario: The account split is documented

- **WHEN** an operator reads the visual role settings in the environment template
- **THEN** an adjacent comment MUST state that the mainland and international Kimi endpoints are separate accounts with separate credentials and currencies

### Requirement: Images are submitted as base64 or file reference, never as a remote URL

The visual inspection model does not accept public HTTP image URLs. The system MUST submit each rendered image either as a base64 data URL in an image content part, or as a provider file reference obtained by uploading the file first.

Request content MUST be a structured list of parts. A serialized string standing in for the parts list MUST NOT be sent.

#### Scenario: A rendered image is submitted as base64

- **WHEN** a locally rendered PNG is inspected
- **THEN** it MUST be submitted as a base64 data URL or a provider file reference

#### Scenario: A remote URL is not used

- **WHEN** an image is inspected
- **THEN** the request MUST NOT reference the image by a public HTTP URL

#### Scenario: Content is a structured part list

- **WHEN** an inspection request is built
- **THEN** its message content MUST be a list of typed parts

### Requirement: Request size limits are respected

Ultra-HD images at high device pixel ratio can be large, and the provider enforces a maximum request body size. The system MUST ensure each inspection request stays within the configured maximum body size, downscaling the submitted copy of the image if necessary.

Downscaling MUST apply only to the copy sent for inspection. The delivered image MUST retain its full rendered resolution.

Downscaling MUST NOT go below a configured minimum at which text defects would stop being detectable, since an unreadably small inspection copy would report a false pass.

#### Scenario: An oversized image is downscaled for inspection only

- **WHEN** a rendered image exceeds the configured maximum request body size
- **THEN** the copy submitted for inspection MUST be downscaled
- **AND** the attached image MUST retain its full rendered resolution

#### Scenario: Downscaling has a floor

- **WHEN** downscaling to fit the body limit would fall below the configured minimum inspection resolution
- **THEN** the image MUST be inspected in segments rather than downscaled below the floor

#### Scenario: A long image is inspected in segments

- **WHEN** the long image is too tall to inspect in one request at usable resolution
- **THEN** it MUST be inspected as multiple segments covering its full height

### Requirement: Per-role cost and latency are recorded

Because the two roles have materially different per-call costs and the visual role always reasons, the system MUST log per run the number of calls made in each role and, where the provider exposes usage, the token counts.

The visual inspection role's call count MUST scale with the number of images and retry attempts, not with the number of digest items, and this relationship MUST be observable from the logs.

#### Scenario: Call counts are logged per role

- **WHEN** a digest run completes
- **THEN** the log MUST record how many calls were made in the text role and how many in the visual role

#### Scenario: Retry cost is visible

- **WHEN** an image required three inspection attempts
- **THEN** the logged visual-role call count MUST reflect all three

#### Scenario: Generation cost is counted per output image

- **WHEN** generation produces images for a run
- **THEN** the log MUST record the number of output images generated, since generation is billed per image rather than per token

### Requirement: The image generation role targets a mainland-reachable host with per-image billing

The image generation role MUST default to a host verified reachable from mainland China without a VPN. It MUST be configured with an explicit model identifier rather than a rolling alias, so an upstream model change cannot silently alter output style or cost.

The system MUST treat generation as billed per output image, not per token, and MUST enforce a configured maximum number of generated images per run so a retry loop cannot multiply spend without bound.

#### Scenario: Default generation host is mainland-reachable

- **WHEN** no base URL override is configured for the generation role
- **THEN** the resolved host MUST be one verified reachable from mainland China

#### Scenario: A pinned model identifier is used

- **WHEN** the generation role resolves its model
- **THEN** the identifier MUST be an explicit dated or pinned identifier rather than a rolling latest alias

#### Scenario: Generated image count is capped per run

- **WHEN** the configured maximum generated images per run has been reached
- **THEN** no further generation request may be made
- **AND** remaining images MUST use the fallback background

#### Scenario: Generation retries do not bypass the cap

- **WHEN** a QA failure would trigger a regeneration that exceeds the per-run generation cap
- **THEN** the regeneration MUST use the fallback background rather than a new generated image
