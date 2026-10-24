# Research Content Discovery

## MODIFIED Requirements

### Requirement: Research profiles combine domain and content-type signals
The system MUST define configurable research profiles covering multimodal models, data/evaluation, agentic applications, principles/methodology, physical/embodied AI, spatial AI, full-stack skill and MCP tooling, and AI creative/marketing tooling. A candidate MUST match at least one domain signal and one relevant content-type or implementation signal before it is considered relevant, except for an explicitly configured profile query.

Adding a profile MUST NOT weaken the two-signal rule. A profile's domain vocabulary MUST consist of qualified phrases discriminative enough that a single hit, paired with any content signal, indicates genuine topical relevance.

#### Scenario: Broad term alone is insufficient
- **WHEN** a repository description contains only `agent` or `dataset` without a relevant AI/domain or implementation signal
- **THEN** the candidate MUST NOT receive a passing relevance grade solely from that term

#### Scenario: Multimodal evaluation project matches
- **WHEN** a repository contains `vision-language` and `benchmark` in its searchable metadata
- **THEN** it MUST be eligible for the multimodal/data-evaluation profile

#### Scenario: An added profile still requires two signals
- **WHEN** a repository's searchable metadata contains `humanoid robot` but no content or implementation signal
- **THEN** it MUST NOT be considered relevant to the `physical-ai` profile

#### Scenario: A candidate outside every profile is still rejected
- **WHEN** a repository matches none of the eight profiles' domain vocabularies
- **THEN** it MUST NOT receive a passing relevance grade

## ADDED Requirements

### Requirement: arXiv category coverage includes robotics
The configured arXiv category set MUST include `cs.RO` so that robotics, embodied, and vision-language-action papers are retrievable. The existing categories MUST be retained; `cs.CV` already covers spatial reconstruction and video generation, so no additional category is required for the `spatial-ai` and `creative-marketing` profiles.

The category set MUST remain operator-configurable, and the default MUST be consistent across the application default, the environment templates, and the container orchestration defaults.

#### Scenario: Robotics papers are retrievable
- **WHEN** the arXiv collector runs with default configuration
- **THEN** `cs.RO` MUST be among the queried categories

#### Scenario: Existing categories are not displaced
- **WHEN** the default category set is read
- **THEN** it MUST still contain `cs.AI`, `cs.CL`, `cs.CV`, `cs.LG`, and `cs.IR`

#### Scenario: Defaults agree across deployment surfaces
- **WHEN** the application default, the environment templates, and the Compose default are compared
- **THEN** they MUST name the same category set

### Requirement: GitHub fallback queries stay narrow for added profiles
The GitHub Search fallback query set MUST include domain-plus-content pairs for each added profile. Every query MUST pair a qualified domain phrase with a content or implementation term; no query may consist of a bare domain word alone. The fallback MUST remain a bounded complement to Trending-first discovery and MUST NOT become the primary channel.

#### Scenario: Added-profile queries are well formed
- **WHEN** the fallback query set is inspected
- **THEN** each query for an added profile MUST contain both a qualified domain phrase and a content or implementation term

#### Scenario: A bare domain word is not a query
- **WHEN** the fallback query set is inspected
- **THEN** no query may consist solely of a term such as `robot`, `3d`, `video`, or `mcp`

#### Scenario: Trending remains the primary channel
- **WHEN** Trending yields enough qualifying candidates for the run
- **THEN** the added fallback queries MUST NOT be required for the digest to reach its target
