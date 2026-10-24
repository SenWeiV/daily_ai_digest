## ADDED Requirements

### Requirement: Every platform has a declared visual and editorial style

The system MUST define, per platform, a declared style covering both the copy and the image: tone, structure, length, title convention, tag convention, colour treatment, type scale, and layout density. Styles MUST be distinguishable — two platforms MUST NOT resolve to the same visual and editorial treatment.

Each platform's declared style MUST be recorded in configuration or code as inspectable data, not embedded only inside a prompt string, so it can be reviewed and changed without rewriting prompts.

#### Scenario: Each platform has its own declared style

- **WHEN** the platform style definitions are inspected
- **THEN** each of the six platforms MUST have its own tone, structure, and visual treatment

#### Scenario: Two platforms do not share one treatment

- **WHEN** the 小红书 style and the Reddit style are compared
- **THEN** they MUST differ in tone, structure, and visual treatment

#### Scenario: Styles are inspectable data

- **WHEN** an operator reviews a platform's style
- **THEN** it MUST be readable as structured data rather than only as prose inside a prompt

### Requirement: Image prompts are generated per platform from the declared style and the day's content

For platforms whose images are generated rather than laid out from a template, the system MUST construct the generation prompt from the platform's declared style plus the day's actual digest content. The prompt MUST be produced automatically per run, not hand-written once and reused unchanged.

A generated image prompt MUST NOT request that the model render any text that must be accurate. Titles, project names, figures, and links MUST be composed by the template layer over the image, because generated text inside an image cannot be verified against the digest.

#### Scenario: A prompt reflects the day's content

- **WHEN** image prompts are constructed for two different days' digests
- **THEN** the prompts MUST differ according to that day's content

#### Scenario: A prompt reflects the platform style

- **WHEN** the 小红书 and X image prompts are compared
- **THEN** they MUST differ according to their declared visual styles

#### Scenario: Accurate text is not delegated to image generation

- **WHEN** an image must display a project name or a figure from the digest
- **THEN** that text MUST be composed by the template layer
- **AND** the generation prompt MUST NOT ask the model to render it

### Requirement: Generated imagery is background and decoration, never the carrier of facts

Where image generation is used, its output MUST serve as background, texture, or decorative illustration beneath or beside template-composed text. The composed result MUST remain legible if the generated layer is replaced or absent.

The generation prompt MUST instruct the provider to leave the regions where template text will be composited visually quiet, so composited text is not laid over high-contrast detail.

The system MUST provide a non-generated fallback background so that a generation failure degrades to a plain designed background rather than to no image.

#### Scenario: Text remains legible over generated background

- **WHEN** a generated background is composited under template text
- **THEN** the text MUST meet the legibility requirement of the visual QA gate

#### Scenario: Text regions are kept visually quiet

- **WHEN** a generation prompt is constructed for an image that will carry composited text
- **THEN** it MUST request low visual complexity in the regions reserved for that text

#### Scenario: Generation failure falls back to a plain background

- **WHEN** image generation fails or is unavailable
- **THEN** the image MUST be composed on the non-generated fallback background
- **AND** MUST still be produced and inspected

#### Scenario: Generation is disable-able

- **WHEN** image generation is disabled in configuration
- **THEN** all images MUST be produced with the fallback background
- **AND** no generation request may be made

### Requirement: Generated output resolution is at least the frame's rendered size

A generated background MUST be requested at a resolution at or above the composited frame's pixel dimensions at the configured device pixel ratio. Upscaling a smaller generated image to fill a frame MUST NOT be used, because the resulting softness is indistinguishable from a rendering defect and would either fail inspection or degrade the delivered image.

Where the provider offers discrete resolution tiers, the system MUST select the smallest tier at or above the required dimensions.

#### Scenario: Generation resolution meets the frame

- **WHEN** a background is generated for a frame whose rendered size is 2484×3312
- **THEN** the requested generation resolution MUST be at or above those dimensions

#### Scenario: Upscaling is not used to fill a frame

- **WHEN** the largest available generation resolution is below the frame's rendered size
- **THEN** the fallback background MUST be used rather than upscaling the generated image

#### Scenario: The smallest sufficient tier is chosen

- **WHEN** several provider resolution tiers exceed the required dimensions
- **THEN** the smallest sufficient tier MUST be selected

### Requirement: A multi-page platform set is visually consistent

When a platform receives more than one image, those images MUST share one visual treatment: the same palette, type scale, and layout system. A reader MUST be able to see the set as one post rather than as unrelated images.

Consistency MUST be achieved by shared template and shared style parameters. Where generated imagery is used across a set, the system MUST use the provider's consistent-series capability, or failing that a shared conditioning image or seed, so the generated layers do not diverge in style across pages.

The generation model selected for a multi-page set MUST be one that supports consistent-series generation. A model that cannot produce a consistent series MUST NOT be used for multi-page platforms.

#### Scenario: The 小红书 set shares one treatment

- **WHEN** the cover and the three content pages are produced
- **THEN** they MUST share palette, type scale, and layout system

#### Scenario: Generated layers in a set do not diverge

- **WHEN** generated backgrounds are used for a multi-page set
- **THEN** the provider's consistent-series capability or a shared conditioning input MUST be used across the set

#### Scenario: A model without series support is not used for a set

- **WHEN** the configured generation model does not support consistent-series generation
- **THEN** it MUST NOT be used for a multi-page platform
- **AND** those pages MUST use the fallback background

### Requirement: Copy and image for a platform agree with each other

A platform's copy and its images MUST be generated from the same selected items in the same order. An item featured on a platform's image MUST appear in that platform's copy, and no image may feature an item the copy omits.

#### Scenario: Featured items match

- **WHEN** a 小红书 content page features three projects
- **THEN** those three projects MUST appear in the 小红书 copy

#### Scenario: Ordering agrees

- **WHEN** copy and images are produced for one platform
- **THEN** they MUST present items in the same order

### Requirement: Generated imagery is subject to the same grounding rule as copy

Image generation prompts MUST NOT introduce a project, figure, claim, or logo that is absent from the digest. A generated image MUST NOT depict a brand mark, product screenshot, or recognisable third-party visual identity that the digest does not contain.

#### Scenario: No fabricated subject in a prompt

- **WHEN** an image generation prompt is constructed
- **THEN** every named subject in it MUST derive from the digest items

#### Scenario: No third-party brand mark is requested

- **WHEN** an image generation prompt is constructed
- **THEN** it MUST NOT request a recognisable third-party logo or brand identity

### Requirement: The image generation provider is configured and its absence is tolerated

The image generation provider MUST be configured with its own model identifier, endpoint, and credential, independent of the text and visual-inspection roles. The provider MUST be reachable from the deployment host without a VPN.

Provider-applied watermarking MUST be off in delivered output. The system MUST expose watermarking as its own configuration setting, that setting MUST default to disabled, and the value MUST be sent explicitly on every generation request rather than left to the provider's default. The provider's own default is `true`, which stamps "AI生成" into the bottom-right corner, so a request that omits the field ships a watermark the operator never chose.

The system MUST run correctly with image generation unconfigured, producing template-composed images on the fallback background.

#### Scenario: Generation is configured independently

- **WHEN** the configuration is read
- **THEN** the generation provider's model, endpoint, and credential MUST resolve independently of the other two roles

#### Scenario: The watermark setting defaults to disabled

- **WHEN** no watermark override is configured
- **THEN** the resolved watermark setting MUST be disabled

#### Scenario: Watermarking is sent explicitly on every request

- **WHEN** a generation request is built
- **THEN** it MUST carry an explicit watermark field
- **AND** MUST NOT rely on the provider's default value

#### Scenario: Unconfigured generation still produces images

- **WHEN** no generation credential is configured
- **THEN** images MUST still be produced on the fallback background and inspected

#### Scenario: Generation latency does not block the email indefinitely

- **WHEN** a generation request exceeds its configured timeout
- **THEN** the fallback background MUST be used for that image

### Requirement: Generated assets are retrieved before their provider URLs expire

A provider that returns generated images as time-limited URLs MUST have its output downloaded to local storage during the run. The system MUST NOT store a provider URL as the source of a delivered image, because the URL will expire while the stored digest persists.

#### Scenario: Generated image is downloaded during the run

- **WHEN** the provider returns a generated image as a URL
- **THEN** the image MUST be downloaded to local storage before the run completes

#### Scenario: A provider URL is not stored as the asset

- **WHEN** a generated image is recorded for a digest
- **THEN** the record MUST reference the local file rather than the provider URL

#### Scenario: A failed download falls back

- **WHEN** downloading a generated image fails
- **THEN** the fallback background MUST be used for that image

### Requirement: Platform image layouts preserve complete content

Platform templates MUST use wrapping, density changes, or additional content pages rather than silently dropping item fields. Small-red-book content pages MUST be generated dynamically for all supplied items, while additional pages MAY reuse a declared stable content-background slot. X image copy MAY show a lead item, but the associated publishable copy MUST retain the complete ordered thread.

#### Scenario: More items require additional content pages

- **WHEN** the digest contains more items than the base page inventory can hold
- **THEN** additional pages MUST be emitted until every selected item is represented
- **AND** every page MUST retain a declared frame size and stable background slot
