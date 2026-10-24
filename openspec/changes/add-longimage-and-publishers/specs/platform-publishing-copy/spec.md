## ADDED Requirements

### Requirement: Per-platform copy is generated for six platforms

The system MUST generate share-ready copy for 小红书, 微信公众号, X, Instagram, 知乎, and Reddit from each day's digest. Each platform's copy MUST be produced in that platform's own conventions rather than the same text relabelled six times.

Copy generation MUST reuse the configured LLM through the existing analysis path. It MUST consume the already-analyzed digest items rather than re-fetching or re-analyzing source content.

#### Scenario: All six platforms receive copy

- **WHEN** a digest is generated with copy generation enabled
- **THEN** copy MUST be produced for each of the six platforms

#### Scenario: Copy is derived from analyzed items

- **WHEN** copy is generated
- **THEN** it MUST be built from the selected digest items and their existing summaries
- **AND** no additional source fetch or per-item analysis pass may be performed

#### Scenario: Platforms are not given identical text

- **WHEN** the copy for 小红书 and the copy for Reddit are compared
- **THEN** they MUST differ in structure and length rather than being the same string

### Requirement: Each platform's copy respects that platform's format

Copy MUST satisfy the constraints of its platform:

- **X**: a single post at or under 280 characters, or an explicitly numbered thread whose every part is at or under 280 characters. Chinese characters MUST be counted as the platform counts them.
- **小红书**: a title at or under 20 characters, a body at or under 1000 characters, and between 3 and 10 hashtags.
- **Instagram**: a caption at or under 2200 characters with hashtags grouped at the end.
- **微信公众号**: a title at or under 64 characters and a body structured with headings suitable for a draft article.
- **知乎**: a long-form answer or article body with no hashtags, since the platform has no hashtag convention.
- **Reddit**: an English title and body in Markdown, with no hashtags and no emoji-led formatting.

A generated item that exceeds its platform's limit MUST be truncated or regenerated rather than emitted over-limit.

#### Scenario: An X post fits the character limit

- **WHEN** X copy is generated
- **THEN** the post, or every part of the thread, MUST be at or under 280 characters

#### Scenario: 小红书 copy carries a valid tag count

- **WHEN** 小红书 copy is generated
- **THEN** it MUST carry between 3 and 10 hashtags
- **AND** its title MUST be at or under 20 characters

#### Scenario: Reddit copy is in English Markdown

- **WHEN** Reddit copy is generated
- **THEN** the title and body MUST be in English
- **AND** the body MUST be Markdown without hashtags

#### Scenario: 知乎 copy carries no hashtags

- **WHEN** 知乎 copy is generated
- **THEN** it MUST NOT contain hashtags

#### Scenario: Over-limit output is corrected before delivery

- **WHEN** generated copy exceeds its platform's limit
- **THEN** it MUST be truncated or regenerated so the delivered copy is within the limit

### Requirement: Generated copy asserts nothing absent from the digest

Copy MUST be grounded in the digest. It MUST NOT introduce a project, paper, video, author, star count, benchmark number, date, or URL that is not present in the digest items it was generated from.

Every link appearing in generated copy MUST be a link already present in the digest.

#### Scenario: No fabricated project

- **WHEN** copy is generated from a digest of eight items
- **THEN** every project, paper, or video named in the copy MUST correspond to one of those eight items

#### Scenario: No fabricated figure

- **WHEN** copy mentions a star count or a benchmark result
- **THEN** that figure MUST match the value stored on the digest item

#### Scenario: No invented link

- **WHEN** copy contains a URL
- **THEN** that URL MUST appear in the digest items

### Requirement: Automated posting is out of scope and no platform credentials are required

The system MUST NOT call any platform publishing API and MUST NOT require or store platform credentials or OAuth tokens. Copy and images are delivered to the operator, who decides what to post.

This boundary is deliberate and reflects two facts: the deployment host cannot reach X, Instagram, or Reddit without a VPN, and 小红书 offers no official publish API while actively restricting automated posting. The delivery-only design therefore works identically regardless of host network reachability.

#### Scenario: No outbound platform request is made

- **WHEN** a digest with copy generation runs to completion
- **THEN** no request may be made to a social platform publishing endpoint

#### Scenario: No platform credential is required to run

- **WHEN** the system runs with no platform credentials configured
- **THEN** copy generation MUST succeed

#### Scenario: Behavior does not depend on reaching foreign platforms

- **WHEN** the host cannot reach X, Instagram, or Reddit
- **THEN** copy for those platforms MUST still be generated and delivered

### Requirement: Copy generation failure degrades to the digest alone

Copy generation MUST NOT be a precondition for delivery. If the LLM is unavailable, returns unusable output, or fails validation, the failure MUST be logged and the digest email MUST still be sent.

When copy for some platforms succeeds and others fail, the successful copy MUST be delivered and the failed platforms MUST be identified in the email rather than silently omitted.

Copy generation MUST be disable-able per platform through configuration.

#### Scenario: LLM unavailable

- **WHEN** the configured LLM is unreachable during copy generation
- **THEN** the failure MUST be logged
- **AND** the digest email MUST still be sent without the copy section

#### Scenario: Partial success is reported

- **WHEN** copy succeeds for four platforms and fails for two
- **THEN** the four MUST be delivered
- **AND** the two failures MUST be named in the email

#### Scenario: A platform is disabled

- **WHEN** a platform is disabled in configuration
- **THEN** no copy may be generated for it
- **AND** its absence MUST NOT be reported as a failure

### Requirement: Copy remains complete without omission markers

Generated copy MUST use complete sentences and MUST NOT contain ellipsis characters, runs of ASCII periods, or repeated Chinese full stops as a substitute for omitted content. Local validation MUST NOT silently shorten an over-limit title, body, or hashtag list. An over-limit draft MUST enter the targeted repair path and, if still invalid, be named as a platform failure.

#### Scenario: A draft exceeds a platform limit

- **WHEN** generated copy exceeds the platform's declared limit
- **THEN** the original draft MUST remain available for targeted repair
- **AND** no shortened version with omitted content may be accepted locally

#### Scenario: A draft contains an omission marker

- **WHEN** a title, body, hashtag, or X thread part contains an omission marker
- **THEN** validation MUST reject that platform draft

### Requirement: X copy is represented as an ordered thread

X copy MUST be represented as an ordered list of thread parts. Every part MUST be validated independently using X's weighted 280-character rule. The email copy section MUST preserve order and identify each part so it can be copied as a thread.

#### Scenario: A multi-part X thread is valid

- **WHEN** every thread part is at or below 280 weighted characters
- **THEN** the thread MUST pass length validation even when all parts combined exceed 280

#### Scenario: One X thread part is too long

- **WHEN** one thread part exceeds 280 weighted characters
- **THEN** validation MUST identify the failing part
- **AND** the thread MUST NOT be silently flattened or shortened
