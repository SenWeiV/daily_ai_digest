# Digest Quality Selection

## ADDED Requirements

### Requirement: Selected candidates have explicit A/B/C grades
The system MUST assign each GitHub and arXiv candidate an explicit quality grade with inspectable evidence. A-grade content MUST be highly relevant, substantive, and supported by concrete method, implementation, experiment, benchmark, or dataset evidence. B-grade content MUST be directly relevant and useful but have incomplete evidence or implementation detail. C-grade content MUST include broad keyword-only matches, generic/marketing content, placeholder projects, duplicates, or insufficient evidence.

#### Scenario: Evidence-backed paper is A-grade
- **WHEN** a paper is directly relevant and its abstract/metadata describes a concrete method and evaluation
- **THEN** it MUST be eligible for A grade

#### Scenario: Relevant but incomplete repository is B-grade
- **WHEN** a repository is directly relevant and has a useful technical README but lacks experiments or implementation evidence
- **THEN** it MAY be graded B and used only after A-grade selection

#### Scenario: Noise is C-grade
- **WHEN** a candidate is a generic news item, duplicate, marketing repository, or keyword-only match
- **THEN** it MUST be graded C and excluded from selection

### Requirement: Dynamic selection uses target and maximum limits
The selector MUST use `target_items=10` and `max_items=24` by default. It MUST select all qualifying A-grade items up to the maximum, then use B-grade items only when A-grade count is below the target. It MUST never use C-grade items to fill a digest.

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

### Requirement: Selection is source-aware and deterministic
The selector MUST deduplicate by stable source keys before grading/selection and SHOULD preserve coverage across research profiles and source/content types when trimming at the maximum. Given the same candidate metadata and configuration, it MUST produce the same ordering and selected set.

#### Scenario: GitHub/arXiv duplicate work
- **WHEN** an arXiv item and GitHub item are explicitly linked to the same work
- **THEN** the selector MUST avoid accidental duplicate entries according to the configured presentation policy while preserving the relation metadata

#### Scenario: Repeated run with same inputs
- **WHEN** the same candidate set and configuration are processed twice
- **THEN** the selected stable keys and ordering MUST be identical

### Requirement: YouTube behavior remains unchanged
The dynamic GitHub/arXiv selector MUST NOT alter YouTube discovery queries, candidate count, analyzer invocation, persisted YouTube payload, or rendering semantics.

#### Scenario: Digest includes all sources
- **WHEN** GitHub or arXiv selection changes the number of research items
- **THEN** the YouTube section MUST retain its existing items and processing behavior

### Requirement: Quality thresholds are explicit, not distribution-fitted
The system MUST use documented evidence rules and configuration values for grading. It MUST NOT infer thresholds by fitting to the score distribution of the current day's candidates.

#### Scenario: Candidate distribution changes
- **WHEN** one day has unusually many or few candidates
- **THEN** grade outcomes MUST still follow the configured evidence rules rather than recalibrating to that day's distribution
