# GitHub Trending Discovery

## ADDED Requirements

### Requirement: Trending is the primary GitHub discovery source

The system MUST retrieve GitHub Trending for the requested daily, weekly, or monthly period before deciding whether another GitHub source is needed. It MUST retain Trending rank and the period-specific recent-Star count. It MUST NOT query repositories by creation date.

#### Scenario: Trending supplies enough qualified projects
- **WHEN** Trending produces at least the configured target number of relevant, non-C projects
- **THEN** the system MUST use those projects as the GitHub candidate set
- **AND** it MUST NOT invoke Repository Search

#### Scenario: No recently-created discovery
- **WHEN** any GitHub Search query is constructed
- **THEN** the query MUST NOT contain a `created:` qualifier

### Requirement: Trending attempts use a global bounded retry budget

The system MUST allow each Trending HTTP attempt up to 120 seconds by default and MUST make no more than 10 total attempts for one requested period. The attempt budget MUST be shared across direct, proxy, and mirror access methods. The first successfully parsed non-empty response MUST stop retries.

#### Scenario: First access method succeeds
- **WHEN** the direct Trending request returns a valid repository list
- **THEN** the system MUST return it after one attempt
- **AND** it MUST NOT contact proxy or mirror methods

#### Scenario: Access methods fail repeatedly
- **WHEN** Trending requests time out or return invalid responses
- **THEN** the system MUST cycle through configured access methods
- **AND** each request MUST respect the per-attempt timeout
- **AND** the total number of attempts MUST NOT exceed 10

#### Scenario: All attempts fail
- **WHEN** all 10 Trending attempts fail
- **THEN** the system MUST log the exhausted attempt budget
- **AND** it MUST continue to the bounded popular-active fallback instead of failing the digest

### Requirement: Popular-active Search is fallback-only

When fewer than the configured target number of qualified Trending projects are available, the system MAY execute narrow research-profile Repository Search queries using a recent `pushed:` window and total-Star ordering. The fallback MUST be bounded by the remaining candidate budget and MUST NOT displace qualified Trending A-grade projects.

#### Scenario: Trending is below target
- **WHEN** six qualified Trending projects remain and the target is ten
- **THEN** the system MAY search recently-pushed relevant repositories
- **AND** fallback candidates MUST only fill the missing positions allowed by quality selection

#### Scenario: Search fails
- **WHEN** fallback Repository Search raises an API or rate-limit error
- **THEN** the system MUST retain the qualified Trending projects
- **AND** GitHub failure MUST NOT prevent arXiv, YouTube, persistence, or email generation

### Requirement: GitHub candidates remain bounded and deduplicated

The system MUST inspect no more than the configured GitHub candidate limit, MUST deduplicate repository objects by numeric GitHub repository ID, and MUST retain explicit arXiv relations.

#### Scenario: Repository appears in multiple Trending paths
- **WHEN** the same repository is returned through more than one access method or fallback query
- **THEN** the system MUST inspect and present it once using its numeric repository ID
