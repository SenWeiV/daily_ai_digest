# Digest Quality Selection

## MODIFIED Requirements

### Requirement: Dynamic selection uses target and maximum limits
The selector MUST use `target_items=10` and `max_items=24` by default. It MUST select all qualifying A-grade items up to the maximum, then use B-grade items only when A-grade count is below the target. It MUST never use C-grade items to fill a digest.

Widening the profile set MUST NOT change these limits. The intended volume is unchanged and is recorded here explicitly: a run that qualifies more A-grade items across a wider topic space is expected to produce a larger digest, up to 24 items. The 10-item target remains a floor to reach, not a ceiling to trim to, and no per-topic quota or admission threshold may be introduced to hold runs near 10.

#### Scenario: A items below target
- **WHEN** there are 7 A-grade items and at least 3 B-grade items
- **THEN** the selector MUST return 10 items, consisting of all 7 A items and 3 B items

#### Scenario: Many A items
- **WHEN** there are 16 A-grade items
- **THEN** the selector MUST return all 16 A items

#### Scenario: More than maximum
- **WHEN** there are 30 A-grade items
- **THEN** the selector MUST return exactly 24 A items using deterministic coverage and evidence tie-breakers

#### Scenario: Too few qualifying items
- **WHEN** there are 4 A-grade items and 2 B-grade items
- **THEN** the selector MUST return 6 items and MUST NOT add C-grade items

#### Scenario: A wider topic space produces a larger digest
- **WHEN** the added profiles qualify 18 A-grade items where the previous profile set would have qualified 9
- **THEN** the selector MUST return all 18 items rather than trimming toward the 10-item target

### Requirement: Selection is source-aware and deterministic
The selector MUST deduplicate by stable source keys before grading/selection and SHOULD preserve coverage across research profiles and source/content types when trimming at the maximum. Given the same candidate metadata and configuration, it MUST produce the same ordering and selected set.

Determinism MUST hold as the profile set grows. A candidate carrying several research topics MUST NOT gain rank purely from the topic count, and the ordering MUST NOT depend on the iteration order of the profile registry.

#### Scenario: GitHub/arXiv duplicate work
- **WHEN** an arXiv item and GitHub item are explicitly linked to the same work
- **THEN** the selector MUST avoid accidental duplicate entries according to the configured presentation policy while preserving the relation metadata

#### Scenario: Repeated run with same inputs
- **WHEN** the same candidate set and configuration are processed twice
- **THEN** the selected stable keys and ordering MUST be identical

#### Scenario: Multi-topic items do not outrank on topic count alone
- **WHEN** two A-grade items have equal evidence and one carries three research topics while the other carries one
- **THEN** the tie MUST be broken by the existing deterministic keys and MUST NOT be broken by topic count

## ADDED Requirements

### Requirement: Topic breadth is preserved when A-grade items exceed the maximum
When more A-grade items qualify than `max_items` permits, the selector MUST admit at least one item from every represented research topic before admitting a second item from any topic, and MUST continue in that round-robin manner until the maximum is reached. Within a topic, the existing deterministic evidence and coverage ordering MUST decide which item is taken.

This rule MUST be a trimming rule only. It MUST NOT reject an item that would otherwise be selected when the qualifying count is at or below the maximum, and it MUST NOT introduce a per-topic quota.

#### Scenario: One popular topic cannot occupy the whole digest
- **WHEN** 30 A-grade items qualify, 25 of them tagged `physical-ai` and one each tagged five other topics
- **THEN** the 24 selected items MUST include the item from each of the five other topics
- **AND** the remaining slots MUST be filled from `physical-ai` in deterministic order

#### Scenario: Trimming does not apply below the maximum
- **WHEN** 12 A-grade items qualify and 11 of them share one topic
- **THEN** all 12 items MUST be selected

#### Scenario: Round-robin order is deterministic
- **WHEN** the same over-maximum candidate set is processed twice
- **THEN** the selected set and its ordering MUST be identical

### Requirement: Grade rules are unchanged by the added profiles
The A/B/C evidence rules and the social-proof gates MUST NOT be relaxed, tightened, or made profile-specific to accommodate the added topic areas. A candidate in an added profile MUST clear the same evidence bar as one in an existing profile.

#### Scenario: An added-profile candidate faces the same bar
- **WHEN** a `spatial-ai` repository matches its profile but has no substantive README, topics, implementation, or paper link
- **THEN** it MUST be graded C exactly as an equivalent `multimodal` repository would be

#### Scenario: No profile receives a grading exemption
- **WHEN** the grading rules are inspected
- **THEN** no rule may branch on which profile a candidate matched
