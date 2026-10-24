## ADDED Requirements

### Requirement: The email structure supports attachments without displacing the body

The digest email is currently a two-part alternative container holding plain text and HTML, which cannot carry attachments. The system MUST restructure the message so that attachments are carried alongside the body rather than in place of it: a mixed container MUST wrap the existing plain-and-HTML alternative part, and attachments MUST be siblings of that part.

Both the plain-text and HTML bodies MUST be retained. A client that renders only plain text MUST still receive readable content.

#### Scenario: Attachments and body coexist

- **WHEN** an email is sent with rendered images attached
- **THEN** the HTML body MUST render as the message body
- **AND** the images MUST appear as attachments

#### Scenario: Plain-text alternative is retained

- **WHEN** the message structure is inspected
- **THEN** it MUST contain both a plain-text part and an HTML part inside an alternative container

#### Scenario: No attachments still sends a valid message

- **WHEN** rendering is disabled or produced no images
- **THEN** the email MUST still be a valid message with both body parts

### Requirement: Rendered images are attached with meaningful filenames

Rendered images MUST be attached with filenames that identify what each one is for, so the operator can pick the right file without opening all of them. The long image MUST be attached as `digest-full.png`, and platform images MUST use their platform-identifying names.

Attachment filenames MUST include the digest date so files saved from successive days do not overwrite one another.

#### Scenario: Long image is identifiable

- **WHEN** the long image is attached
- **THEN** its filename MUST identify it as the full digest image and MUST include the digest date

#### Scenario: Platform images are distinguishable

- **WHEN** the platform images are attached
- **THEN** each filename MUST identify its target platform and dimensions purpose

#### Scenario: Successive days do not collide

- **WHEN** two days' emails are saved to one folder
- **THEN** the filenames MUST NOT collide

### Requirement: Per-platform copy appears in its own section after the main content

The email MUST present the per-platform copy in a distinct section placed after the existing digest content, not interleaved with it. The main digest MUST remain the first thing the reader sees.

Each platform MUST appear as its own labelled block containing its copy, and each block MUST name the image file that belongs with it. Copy MUST be presented as selectable plain text so it can be copied into the platform without picking up email styling.

#### Scenario: Main content comes first

- **WHEN** the email is rendered
- **THEN** the GitHub, arXiv, and YouTube sections MUST appear before the platform copy section

#### Scenario: Each platform is a labelled block

- **WHEN** the platform copy section is rendered
- **THEN** each enabled platform MUST appear as a separately labelled block

#### Scenario: Copy is copy-pasteable

- **WHEN** a reader selects a platform's copy
- **THEN** the selection MUST yield the plain copy text without surrounding markup artifacts

#### Scenario: Blocks reference their images

- **WHEN** a platform has an associated rendered image
- **THEN** its block MUST name that image's attachment filename

### Requirement: Existing digest presentation is unchanged

The main digest body MUST render exactly as it does today. Adding attachments and the platform copy section MUST NOT alter the existing sections' markup, ordering, styling, or item content.

#### Scenario: Existing sections are untouched

- **WHEN** a digest is rendered with the new packaging
- **THEN** the existing GitHub, arXiv, and YouTube section markup MUST be unchanged

#### Scenario: Item content is unchanged

- **WHEN** the same digest is rendered before and after this change
- **THEN** the items shown and their summaries MUST be identical

### Requirement: One email carries the digest, the copy, and the images

The digest content, the per-platform copy, and every rendered image MUST be delivered in a single email. The system MUST NOT split the digest and its assets across two or more messages, and MUST NOT send the digest first and the assets later.

Because the QA gate may require several render-and-inspect cycles, the send MUST wait until every image has either passed inspection or been withheld. Waiting longer is required; sending early is not permitted.

#### Scenario: Everything arrives together

- **WHEN** a digest with copy and images is delivered
- **THEN** exactly one email MUST be sent containing the digest body, the copy section, and the passing images

#### Scenario: The send waits for the QA gate

- **WHEN** images are still in the render-and-inspect cycle
- **THEN** the email MUST NOT be sent until the cycle has completed for every image

#### Scenario: A slow QA cycle does not cause a second email

- **WHEN** the QA cycle takes substantially longer than a render alone would
- **THEN** the system MUST still send exactly one email

#### Scenario: Withheld images do not trigger a follow-up message

- **WHEN** an image is withheld after failing inspection
- **THEN** no separate email may be sent to deliver it later

### Requirement: Packaging failures degrade to the current email

Every addition in this capability MUST be individually skippable at send time. A failure to attach, to render, or to generate copy MUST result in an email that is at worst identical to today's, and MUST NOT result in no email.

The system MUST log which optional parts were omitted and why.

#### Scenario: Attachment step fails

- **WHEN** attaching a rendered image raises an error
- **THEN** the email MUST still be sent without that attachment

#### Scenario: Everything optional fails

- **WHEN** both rendering and copy generation fail
- **THEN** the email MUST be sent with exactly its current content

#### Scenario: Omissions are logged

- **WHEN** an optional part is omitted
- **THEN** the omission and its cause MUST be logged
