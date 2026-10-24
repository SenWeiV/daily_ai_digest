## ADDED Requirements

### Requirement: Public reads do not grant mail or paid-generation access
Mutating API routes SHALL require a configured administrator bearer key. Empty configuration MUST disable management actions. The frontend MUST NOT embed the key in public build assets.

#### Scenario: Unauthenticated trigger
- **WHEN** a request tries to generate a digest, send test mail, or change configuration without a valid key
- **THEN** the API rejects the action before running it

### Requirement: Delivery results are truthful and durable
The service SHALL persist whether delivery is pending, sending, sent, failed, partial, or unknown. It MUST report failed requested delivery as a failed execution. Regeneration MUST clear stale sent status.

#### Scenario: SMTP rejects all recipients
- **WHEN** SMTP definitively rejects delivery
- **THEN** the record remains unsent, execution fails, and a later non-forced request can reuse saved content

#### Scenario: Partial or uncertain delivery
- **WHEN** only some recipients are accepted or DATA acceptance cannot be determined
- **THEN** the service records a partial or unknown outcome and prevents non-forced duplicate delivery

#### Scenario: Already delivered content
- **WHEN** a non-forced request finds a sent record
- **THEN** it returns the record without sending another message

### Requirement: Attachment budgets include dynamic pages
The budget SHALL include every generated page, including dynamically numbered platform pages, and discard small-red-book content pages from the end before withholding the main digest image.

#### Scenario: More than three content pages
- **WHEN** the image set includes content pages 1 through 10 and exceeds the budget
- **THEN** pages 10 through 2 are considered before page 1 and the main digest image

### Requirement: Real acceptance testing is isolated
The acceptance run SHALL collect real sources, generate the current enabled content, send one uniquely identified message, and verify that exact message from a readable recipient mailbox without altering scheduled records.

#### Scenario: Successful acceptance
- **WHEN** the operator runs the isolated acceptance command
- **THEN** the scheduled database and permanent feature switches remain unchanged and the report distinguishes SMTP acceptance from mailbox receipt
