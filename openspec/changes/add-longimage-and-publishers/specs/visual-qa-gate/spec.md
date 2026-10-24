## ADDED Requirements

### Requirement: No image is delivered until it passes automated visual QA

Every rendered image MUST pass an automated visual inspection before it is eligible for delivery. The inspection MUST be performed by a vision-capable model that receives the rendered image itself, not the HTML or the data it was rendered from.

The inspection MUST check at minimum:

- absence of missing-glyph boxes (tofu) anywhere in the image
- absence of text clipped at a frame edge or overflowing its container
- absence of overlapping or occluded text
- legibility of all body text at the image's intended viewing size
- presence of every text field the template was given, none silently dropped

An image that fails any check MUST NOT be delivered in that state.

#### Scenario: Tofu boxes block delivery

- **WHEN** the inspection detects missing-glyph boxes in a rendered image
- **THEN** that image MUST NOT be attached to the email in that state

#### Scenario: Clipped text blocks delivery

- **WHEN** the inspection detects text cut off at a frame edge
- **THEN** that image MUST NOT be attached to the email in that state

#### Scenario: A clean image passes

- **WHEN** the inspection finds no defect in any checked category
- **THEN** the image MUST be eligible for delivery

#### Scenario: The inspection reads the rendered image

- **WHEN** the inspection runs
- **THEN** the rendered image MUST be submitted to the vision model as image input
- **AND** the check MUST NOT be performed by inspecting the source HTML alone

### Requirement: A failed image is regenerated and re-inspected

When an image fails inspection, the system MUST regenerate it and inspect the new output. Each regeneration MUST act on the reported defect rather than repeating the identical render: a font-coverage defect MUST trigger a font fallback, and an overflow or clipping defect MUST trigger tighter truncation or a smaller type scale for the affected field.

The regenerate-and-inspect cycle MUST be bounded by a configured maximum attempt count. Latency is an acceptable cost of correctness; the cycle MUST NOT be skipped to save time.

#### Scenario: A defect triggers a corrective regeneration

- **WHEN** an image fails inspection for text overflow
- **THEN** the regeneration MUST apply tighter truncation or a smaller type scale to the overflowing field
- **AND** the regenerated image MUST be inspected again

#### Scenario: A repeated identical render is not a retry

- **WHEN** an image fails inspection
- **THEN** the next attempt MUST differ from the failed attempt in the parameter targeting the reported defect

#### Scenario: Attempts are bounded

- **WHEN** an image has failed inspection the configured maximum number of times
- **THEN** no further regeneration may be attempted for that image

#### Scenario: A later attempt passing is sufficient

- **WHEN** an image fails the first inspection and passes the second
- **THEN** the passing image MUST be eligible for delivery

### Requirement: An image that never passes is withheld, and its absence is stated

When the bounded retry cycle ends with an image still failing inspection, that image MUST be withheld from the email entirely. A defective image MUST NEVER be delivered as a degraded or partial result.

The email MUST NOT be cancelled because an image was withheld. It MUST be sent with the images that passed, and it MUST name each withheld image and the defect category that caused it to be withheld, so the reader knows an asset is missing rather than assuming none was produced.

#### Scenario: A persistently failing image is dropped, not shipped

- **WHEN** an image still fails inspection after the maximum attempts
- **THEN** it MUST NOT be attached to the email
- **AND** the email MUST still be sent

#### Scenario: The withheld image is named

- **WHEN** an image is withheld
- **THEN** the email MUST state which image was withheld and the defect category responsible

#### Scenario: Other images are unaffected

- **WHEN** one platform image is withheld and the others passed
- **THEN** the passing images MUST be attached

#### Scenario: A withheld image is never silently replaced

- **WHEN** an image is withheld
- **THEN** no placeholder or lower-quality substitute may be attached in its place

### Requirement: Font coverage is verified before rendering, not only after

Missing-glyph boxes are a font-availability defect, and the inspection is a backstop rather than the primary defence. The system MUST verify at startup that a Simplified Chinese font and a color emoji font are installed and resolvable by the rendering engine, and MUST log the resolved font family names.

When a required font is absent, the system MUST log this as an error and MUST NOT attempt to render images, because every output would fail inspection.

#### Scenario: Missing font is detected before rendering

- **WHEN** no Simplified Chinese font is resolvable by the rendering engine
- **THEN** the system MUST log an error
- **AND** MUST NOT attempt image rendering for that run

#### Scenario: Resolved fonts are logged

- **WHEN** the renderer initializes with the required fonts present
- **THEN** the log MUST name the resolved Simplified Chinese and emoji font families

#### Scenario: Every character in the digest has coverage

- **WHEN** digest text contains a character outside the primary font's coverage
- **THEN** a fallback font MUST be applied so the character renders as a glyph

### Requirement: QA verdicts are structured, logged, and auditable

The inspection MUST return a structured verdict per image identifying pass or fail, the failing categories, and a short description of each defect's location. Verdicts MUST be logged for every attempt of every image so a recurring defect is diagnosable from logs without re-running the pipeline.

A verdict that cannot be parsed MUST be treated as a failure, never as a pass.

#### Scenario: Verdict identifies the defect category

- **WHEN** an image fails inspection
- **THEN** the verdict MUST name the failing category and where the defect appears

#### Scenario: Every attempt is logged

- **WHEN** an image required three attempts
- **THEN** all three verdicts MUST appear in the logs

#### Scenario: An unparseable verdict is a failure

- **WHEN** the vision model returns output that cannot be parsed into a verdict
- **THEN** the attempt MUST be treated as a failure
- **AND** MUST NOT be treated as a pass

#### Scenario: Vision model unavailable

- **WHEN** the vision model is unreachable
- **THEN** no image may be marked as passing
- **AND** the email MUST be sent without the unverified images rather than with them
