# GitHub Social Proof Selection

## ADDED Requirements

### Requirement: GitHub candidates expose inspectable popularity metadata

For each bounded GitHub candidate, the system MUST retain total Stars, forks, watchers, open issues, source channel, Trending rank, Trending period, period recent Stars, and recent-Star velocity when available. It MUST count Issue/PR comments from the configured recent window and MUST stop after the configured comment limit.

#### Scenario: Trending metadata is available
- **WHEN** a weekly Trending item reports 700 Stars this week at rank 3
- **THEN** the candidate MUST retain period `weekly`, rank `3`, recent Stars `700`, and velocity `100` Stars per day

#### Scenario: Recent comments exceed the cap
- **WHEN** a repository has more than 100 Issue/PR comments in the configured 14-day window
- **THEN** the system MUST store `100` as the bounded observed count
- **AND** it MUST stop iterating the paginated endpoint

#### Scenario: Comment API is unavailable
- **WHEN** recent Issue/PR comments cannot be retrieved
- **THEN** the system MUST store the metric as unavailable rather than zero
- **AND** it MUST continue with cheap repository activity fields

### Requirement: Research relevance remains mandatory

A GitHub candidate MUST match at least one configured research profile using both domain and content/implementation signals before popularity can qualify it. Popularity alone MUST NOT admit an unrelated project.

#### Scenario: Highly starred unrelated project
- **WHEN** a Trending repository has high recent and total Stars but does not match any research profile
- **THEN** it MUST receive grade C and MUST NOT appear in the digest

### Requirement: Quality grades use social proof without a total-Star floor

The system MUST assign explicit A/B/C grades without a fitted or weighted score. Total Stars MUST NOT be an admission threshold.

A-grade GitHub content MUST be research-relevant, originate from Trending, have observed recent-Star growth, and have demonstrated social activity. The default direct activity evidence is at least five recent Issue/PR comments; when that endpoint is unavailable, multiple cheap repository activity signals MAY establish fallback social proof.

B-grade GitHub content MUST be research-relevant and either be a Trending project with observed recent-Star growth but weak/unavailable conversation evidence, or be a socially proven popular-active fallback without an observed Trending gain.

C-grade GitHub content MUST include unrelated, keyword-only, duplicate, placeholder/marketing, or candidates without observable popularity/social proof.

#### Scenario: Small but rapidly rising project
- **WHEN** a relevant Trending project has no configured total-Star minimum, positive recent-Star growth, and at least five recent comments
- **THEN** it MUST be eligible for grade A regardless of its absolute total Stars

#### Scenario: Mature fallback project
- **WHEN** a relevant recently-pushed fallback repository has high total Stars and active recent comments but no Trending recent-Star observation
- **THEN** it MUST be eligible for grade B but not A

#### Scenario: README-only repository
- **WHEN** a relevant repository has a substantive README and implementation files but no Trending gain or social activity evidence
- **THEN** those implementation signals MUST remain auxiliary
- **AND** the repository MUST NOT receive grade A from completeness alone

### Requirement: GitHub ordering is deterministic and popularity-first

GitHub candidates MUST be ordered lexicographically by quality grade, Trending source before fallback, recent-Star velocity, recent Issue/PR comments, total Stars, forks/watchers/open issues, supporting implementation evidence, recency, and stable key. The system MUST NOT combine these signals into a fitted popularity score.

#### Scenario: Recent momentum outranks total size
- **WHEN** two relevant A-grade Trending projects differ such that one has higher recent-Star velocity and the other has higher total Stars
- **THEN** the higher-velocity project MUST rank first

#### Scenario: Momentum is equal
- **WHEN** recent-Star velocity is equal
- **THEN** recent comments and then total Stars MUST break the tie deterministically

### Requirement: New metadata is backward-compatible and correctly presented

New GitHub popularity fields MUST have backward-compatible defaults when old digest JSON is loaded. Email and frontend views MUST label the recent-Star period correctly and SHOULD display recent comments and total Stars without changing arXiv or YouTube rendering.

#### Scenario: Legacy digest row
- **WHEN** an old GitHub item lacks Trending and social-proof fields
- **THEN** API deserialization and historical views MUST succeed with default or unavailable values

#### Scenario: Weekly recent Stars
- **WHEN** a weekly Trending item reports 700 period Stars
- **THEN** presentation MUST label the value as weekly rather than today's Stars
