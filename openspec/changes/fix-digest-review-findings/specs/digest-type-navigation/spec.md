## ADDED Requirements

### Requirement: Record reads honor the selected digest type
The latest and dated record APIs SHALL accept daily, weekly, or monthly and return only that type. The dashboard SHALL reload when the selected type changes and discard stale responses.

#### Scenario: Weekly selected
- **WHEN** the reader selects the weekly view
- **THEN** the dashboard loads the latest weekly record, even if a newer daily record exists

#### Scenario: Invalid type
- **WHEN** an unsupported digest type is requested
- **THEN** the API returns a validation error

### Requirement: The published HTTPS dashboard has an HTTPS API entry point
The Pages build SHALL use a configured HTTPS API or the project's dedicated HTTPS edge entry point. The edge SHALL forward only application paths to a fixed origin and support the dashboard's CORS requests without caching digest responses.

#### Scenario: Legacy HTTP build variable
- **WHEN** a published build still has an HTTP API variable
- **THEN** the build uses the HTTPS edge entry point to avoid browser mixed-content blocking
