## ADDED Requirements

### Requirement: The digest renders as an ultra-HD long image

The system MUST render the daily digest as a single tall PNG named `digest-full.png`, produced from the same HTML the email body uses so the image and the email cannot disagree about content. The render MUST use a device pixel ratio of at least 2 so text is legible when the image is viewed at full size or re-uploaded by a platform that recompresses.

The render MUST be deterministic for a given digest: two renders of the same stored digest MUST produce images of identical dimensions.

#### Scenario: A digest produces one long image

- **WHEN** a digest containing GitHub, arXiv, and YouTube sections is rendered
- **THEN** a single `digest-full.png` MUST be produced containing every item present in the email body

#### Scenario: The image is high resolution

- **WHEN** the renderer runs with default configuration
- **THEN** the output MUST be rendered at a device pixel ratio of at least 2

#### Scenario: Rendering the same digest twice agrees

- **WHEN** the same stored digest is rendered twice
- **THEN** both outputs MUST have identical pixel dimensions

### Requirement: Tall pages are captured in segments and stitched

Headless Chromium cannot capture a screenshot taller than its maximum texture dimension of 16384 pixels; beyond that the capture silently truncates or fails. The system MUST capture any page taller than a configured safe segment height as multiple sequential screenshots and stitch them vertically into one image.

Segment boundaries MUST NOT drop or duplicate any pixel row. The stitched output height MUST equal the full page height at the render scale.

#### Scenario: A page taller than the texture limit is captured fully

- **WHEN** the rendered page height at the configured scale exceeds 16384 pixels
- **THEN** the capture MUST be performed in multiple segments
- **AND** the stitched output MUST contain the full page height

#### Scenario: Segments join without loss or overlap

- **WHEN** a page is captured as three segments
- **THEN** the stitched height MUST equal the sum of the segment heights
- **AND** no content row may appear twice

#### Scenario: A short page is captured in one pass

- **WHEN** the rendered page height is below the safe segment height
- **THEN** the capture MUST be a single screenshot with no stitching

### Requirement: Chinese text and emoji render as glyphs

The digest content is Chinese and the template uses emoji. The rendering environment MUST provide a CJK font covering Simplified Chinese and a color emoji font in a bitmap format the renderer supports. The rendered image MUST NOT contain replacement boxes in place of Chinese characters or emoji.

The rendering environment MUST be configured so that shared-memory exhaustion does not crash the browser process.

#### Scenario: Chinese characters render

- **WHEN** a digest whose summaries are in Simplified Chinese is rendered
- **THEN** the output MUST NOT contain missing-glyph boxes where Chinese characters appear

#### Scenario: Emoji render in color

- **WHEN** the template's emoji are rendered
- **THEN** they MUST appear as glyphs rather than as missing-glyph boxes

#### Scenario: Fonts are present in the runtime image

- **WHEN** the container image is inspected
- **THEN** a Simplified Chinese font and a color emoji font MUST both be installed

#### Scenario: Missing glyphs are a delivery-blocking defect

- **WHEN** a rendered image contains a missing-glyph box
- **THEN** that image MUST NOT be delivered
- **AND** it MUST be regenerated under the visual QA gate

#### Scenario: Browser does not crash on limited shared memory

- **WHEN** the renderer launches inside a container with a small default shared-memory allocation
- **THEN** the browser MUST be launched with shared-memory usage disabled

### Requirement: Platform-sized images are produced at exact dimensions

The system MUST produce five additional images derived from the same digest data, each at exactly the dimensions each platform expects:

- `xhs-cover.png` at 1242×1656
- `xhs-content-1.png`, `xhs-content-2.png`, `xhs-content-3.png` at 1242×1656
- `x-card.png` at 1600×900
- `ig-square.png` at 1080×1080

Each image MUST be produced at the configured device pixel ratio, so the stored pixel dimensions are the listed dimensions multiplied by that ratio while the aspect ratio is exact. Content MUST be laid out to fit the frame; text MUST NOT be clipped at a frame edge.

When the digest holds more items than the three 小红书 content pages can show, the pages MUST carry the highest-ranked items in the digest's existing order and the remainder MUST be omitted rather than compressed to illegibility.

#### Scenario: Every platform image has the expected aspect ratio

- **WHEN** the five platform images are produced
- **THEN** each MUST match its listed aspect ratio exactly

#### Scenario: Content fits the frame

- **WHEN** an item's title is long enough to overflow its frame
- **THEN** it MUST be truncated with an ellipsis rather than clipped mid-glyph at the frame edge

#### Scenario: More items than pages

- **WHEN** the digest holds 24 items and three 小红书 content pages are produced
- **THEN** the pages MUST carry the highest-ranked items in digest order
- **AND** the omitted items MUST NOT cause a render failure

#### Scenario: Fewer items than pages

- **WHEN** the digest holds fewer items than the three content pages would fill
- **THEN** the unused pages MUST be omitted rather than emitted blank

### Requirement: Rendered output has a size budget and a retention rule

Rendered images MUST be written under the existing data volume. The system MUST enforce a configured total size budget for the images attached to one email. When the budget is exceeded, the system MUST attach the long image and drop platform images in a documented order rather than sending an email that a mail server will reject.

The system MUST delete rendered images older than a configured retention window so daily ultra-HD output cannot fill the disk.

#### Scenario: Attachment budget is respected

- **WHEN** the total size of rendered images exceeds the configured budget
- **THEN** the long image MUST be retained
- **AND** platform images MUST be dropped in the documented order until the total fits

#### Scenario: Old renders are removed

- **WHEN** rendered images older than the retention window exist
- **THEN** they MUST be deleted

#### Scenario: Retention does not delete the current run

- **WHEN** retention cleanup runs during a digest
- **THEN** the images for the current digest MUST NOT be deleted

### Requirement: A rendering failure never blocks the digest email

Image rendering MUST be treated as an enhancement to delivery, not a precondition for it. Any rendering failure — a browser launch failure, a timeout, a missing font, an exhausted disk — MUST be logged and MUST NOT prevent the digest email from being sent.

Rendering MUST be disable-able through configuration so an operator can switch it off with a restart and no code change.

#### Scenario: Browser fails to launch

- **WHEN** the headless browser cannot start
- **THEN** the failure MUST be logged
- **AND** the digest email MUST still be sent with its HTML body

#### Scenario: One platform image fails

- **WHEN** a single platform image fails to render but the long image succeeds
- **THEN** the email MUST be sent with the images that did succeed

#### Scenario: Rendering is disabled by configuration

- **WHEN** rendering is disabled
- **THEN** no browser process may be launched
- **AND** the digest email MUST be sent with its existing content

### Requirement: Generated backgrounds use persistent stable slots

Generated decorative backgrounds MUST be cached by platform slot, frame dimensions, device scale factor, image model, and an explicit cache version. The cache identity MUST NOT include the digest date or daily text, so later digests reuse the same background and update only the overlaid content.

A valid cache hit MUST be checked before provider availability and per-run generation limits. Cached bytes MUST be validated by image signature and decoding, served with their actual MIME type, and written atomically. Corrupt entries MUST be removed and regenerated only for the affected slot.

#### Scenario: A later digest reuses fixed backgrounds

- **WHEN** every requested background slot has a valid cached image
- **THEN** no image-generation provider call MUST be made
- **AND** cache hits MUST NOT consume the per-run generation allowance

#### Scenario: A cached background is corrupt

- **WHEN** one cached slot fails signature or image decoding validation
- **THEN** only that slot MUST be treated as missing
- **AND** the corrupt entry MUST NOT be delivered

#### Scenario: An operator changes the cache version

- **WHEN** the configured background cache version changes
- **THEN** old entries MUST no longer satisfy the new slot identity
