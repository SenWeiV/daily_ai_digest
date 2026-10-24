## ADDED Requirements

### Requirement: Discovery uses the requested business-timezone period
The service SHALL derive a half-open UTC window from the target date and configured timezone. arXiv SHALL query submissions in that window. GitHub SHALL constrain latest push activity to the window. It MUST NOT widen the window to fill the item target.

#### Scenario: Previous day across UTC midnight
- **WHEN** the requested day is 2026-10-23 in Asia/Shanghai
- **THEN** the window starts at 2026-10-22T16:00:00Z and excludes timestamps at or after 2026-10-23T16:00:00Z

### Requirement: Discovery failures do not monopolize preparation time
Trending retrieval SHALL have a total time budget. Generic workflow, memory, or planning terms MUST require a separate AI or MCP signal for Agent matching.

#### Scenario: Trending stalls
- **WHEN** Trending exceeds its total budget
- **THEN** collection proceeds to the search path

#### Scenario: Ordinary software workflow
- **WHEN** a language implementation mentions workflow and framework without AI or MCP context
- **THEN** those terms alone do not classify it as Agent research
