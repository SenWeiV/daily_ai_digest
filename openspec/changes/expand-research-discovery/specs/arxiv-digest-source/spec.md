# arXiv Digest Source

## ADDED Requirements

### Requirement: arXiv retrieval uses configured official feeds
The system MUST retrieve daily paper candidates from configured official arXiv RSS/Atom category feeds. Defaults MUST include `cs.AI`, `cs.CL`, `cs.CV`, `cs.LG`, and `cs.IR`; optional categories MAY be configured. A feed failure MUST be logged and treated as an empty arXiv source without preventing GitHub, YouTube, or persistence from completing.

#### Scenario: Daily categories return papers
- **WHEN** configured arXiv feeds return valid Atom entries
- **THEN** the system MUST parse title, abstract, authors, categories, published time, updated time, version, canonical ID, and canonical URL

#### Scenario: One category is unavailable
- **WHEN** one arXiv category request fails or returns invalid XML
- **THEN** the system MUST log the failure, continue processing other categories, and produce a digest with available sources

### Requirement: arXiv identifiers and category duplicates are normalized
The system MUST normalize versioned IDs such as `2308.03688v3` to stable ID `2308.03688` for deduplication, while preserving the displayed version and published/updated timestamps. An item appearing in multiple category feeds MUST be represented once.

#### Scenario: Version update is received
- **WHEN** `2308.03688v3` is retrieved after `2308.03688v2`
- **THEN** the record MUST retain stable ID `2308.03688`, current version `v3`, and the updated timestamp without creating a second same-work item

#### Scenario: Cross-category duplicate
- **WHEN** one paper appears in both `cs.CV` and `cs.LG`
- **THEN** the system MUST merge the category list under one stable paper record

### Requirement: arXiv records expose source-specific analysis data
The system MUST represent papers separately from GitHub and YouTube items and provide source-specific fields for problem, method, evaluation, results, limitations, and implementation/repository links after analysis. Missing information MUST remain absent or explicitly unknown; the analyzer MUST NOT invent results.

#### Scenario: Paper has no linked code
- **WHEN** a paper contains no explicit GitHub link
- **THEN** its analysis and rendered record MUST remain valid with an empty repository relation

### Requirement: arXiv and GitHub links are explicit
The system MUST extract explicit arXiv IDs/URLs from GitHub metadata and explicit GitHub URLs from paper metadata/links when available. It MUST not merge records solely on title similarity.

#### Scenario: Explicit relation is found
- **WHEN** an arXiv entry includes a GitHub project URL
- **THEN** both records MUST expose the normalized relation key

### Requirement: arXiv data is backward-compatible in persistence and APIs
The system MUST persist selected arXiv items in digest records using an additive nullable/JSON-compatible field. Reading a pre-change database row with no arXiv field MUST return an empty list without migration failure. API, email, and frontend history representations MUST expose an arXiv section while remaining valid for old records.

#### Scenario: Legacy row is loaded
- **WHEN** a digest row created before arXiv support is read
- **THEN** `arxiv_data` MUST deserialize as an empty list and GitHub/YouTube data MUST remain unchanged

#### Scenario: New row is rendered
- **WHEN** a digest contains selected arXiv items
- **THEN** the API and email MUST render them in a distinct arXiv section with canonical paper links
