# Research Content Discovery

## ADDED Requirements

### Requirement: Research profiles combine domain and content-type signals
The system MUST define configurable research profiles covering multimodal models, data/evaluation, agentic applications, and principles/methodology. A candidate MUST match at least one domain signal and one relevant content-type or implementation signal before it is considered relevant, except for an explicitly configured profile query.

#### Scenario: Broad term alone is insufficient
- **WHEN** a repository description contains only `agent` or `dataset` without a relevant AI/domain or implementation signal
- **THEN** the candidate MUST NOT receive a passing relevance grade solely from that term

#### Scenario: Multimodal evaluation project matches
- **WHEN** a repository contains `vision-language` and `benchmark` in its searchable metadata
- **THEN** it MUST be eligible for the multimodal/data-evaluation profile

### Requirement: GitHub discovery has bounded complementary channels
The system MUST collect GitHub candidates from Trending, recently created Repository Search results, and recently updated research repositories. Each channel MUST have an independent configured query/window/candidate limit, and the combined result MUST be deduplicated by numeric repository ID.

#### Scenario: Recently created project is discoverable
- **WHEN** a relevant repository was created within the configured new-project window and matches a narrow profile query
- **THEN** it MUST enter the candidate pool even if it is not in Trending and has few or no new Stars

#### Scenario: Unrelated fallback is not used
- **WHEN** no repository passes the configured relevance and evidence checks
- **THEN** the system MUST return no GitHub candidate rather than filling the list with unrelated Trending repositories

### Requirement: New projects require value evidence
A recently created GitHub repository MUST provide at least one substantive value signal beyond a broad keyword. Accepted signals MUST include one or more of: a substantive README, relevant Topics, implementation files, tests/examples, benchmark/evaluation artifacts, dataset artifacts, an explicit paper link, or a concrete technical description. Empty, placeholder, marketing-only, or unrelated repositories MUST be rejected as C-grade.

#### Scenario: New project with implementation evidence passes
- **WHEN** a new repository matches a research profile and contains a substantive README plus implementation or evaluation artifacts
- **THEN** the candidate MUST be eligible for A or B grading

#### Scenario: New keyword-only project is rejected
- **WHEN** a new repository matches `ai` in its name but has no substantive description, README, topics, code, tests, data, or paper link
- **THEN** it MUST be graded C and MUST NOT be used as digest filler

### Requirement: Candidate retrieval is separated from deep analysis
The system MUST retrieve bounded metadata candidates, apply cheap relevance/evidence checks, deduplicate and grade them before invoking expensive deep analysis. Deep analysis MUST run only for candidates selected for the digest.

#### Scenario: Candidate expansion does not multiply model calls
- **WHEN** the candidate pool grows beyond the daily target
- **THEN** the number of deep analyzer calls MUST be bounded by the final selected item count, not the raw candidate count

### Requirement: Explicit paper and repository relationships are preserved
The system MUST associate a GitHub repository and an arXiv paper only when an explicit arXiv identifier or URL is found in the repository/paper metadata. Title similarity MAY be retained as a hint but MUST NOT merge or suppress either item.

#### Scenario: README contains arXiv URL
- **WHEN** a repository README contains `https://arxiv.org/abs/2308.03688`
- **THEN** the repository and normalized arXiv record MUST expose a relation key for display and deduplication decisions

#### Scenario: Similar titles without links
- **WHEN** a repository and paper have similar titles but neither contains an explicit cross-link
- **THEN** both MUST remain independent candidates
