## ADDED Requirements

### Requirement: The digest calls a single configured LLM provider

The system MUST read the model identifier and API base URL from configuration and MUST send analysis requests to that endpoint through the OpenAI-compatible chat completions path. The default configuration MUST name DeepSeek V4 Flash and the DeepSeek API host. The system MUST NOT retain a fallback model chain by default.

#### Scenario: Default configuration targets DeepSeek

- **WHEN** no model or base URL override is present in the environment
- **THEN** the request MUST carry model `deepseek-v4-flash`
- **AND** the request MUST target the DeepSeek chat completions endpoint derived from `https://api.deepseek.com`

#### Scenario: Operator overrides the model

- **WHEN** an operator sets an explicit model identifier in the environment
- **THEN** the configured value MUST be used verbatim without provider-specific rewriting

#### Scenario: No fallback chain is configured

- **WHEN** the fallback model list is empty
- **THEN** the system MUST attempt exactly one model
- **AND** a request failure MUST surface as an analysis failure for that item rather than a silent retry against a different model

### Requirement: Endpoint construction tolerates both documented base URL forms

DeepSeek documents both `https://api.deepseek.com` and `https://api.deepseek.com/v1` as valid. The system MUST produce exactly one `/chat/completions` suffix for either form and MUST NOT emit a doubled version segment.

#### Scenario: Base URL without a version segment

- **WHEN** the base URL is `https://api.deepseek.com`
- **THEN** the resolved endpoint MUST be `https://api.deepseek.com/v1/chat/completions`

#### Scenario: Base URL already carrying a version segment

- **WHEN** the base URL is `https://api.deepseek.com/v1`
- **THEN** the resolved endpoint MUST be `https://api.deepseek.com/v1/chat/completions`

#### Scenario: Base URL with a trailing slash

- **WHEN** the base URL ends with a slash
- **THEN** the resolved endpoint MUST NOT contain a doubled slash before `chat/completions`

### Requirement: The request body carries only the model and the messages

The system MUST send only the model identifier and the message list in the chat completions request body. It MUST NOT send a sampling temperature, an output token cap, a context limit, or any other generation parameter, so that every such parameter takes the provider's own default. Providers whose thinking mode is on by default MUST therefore keep thinking enabled without the system asking for it.

Rationale for the prohibition, which is not a style preference: an output cap truncates the answer on a long README, and a truncated JSON answer fails to parse and is recorded as an empty analysis rather than as an error. A hardcoded temperature is rejected outright by some models — `kimi-k3` returns `invalid temperature: only 1 is allowed for this model` — and for the vision role that rejection withholds every image, not merely one.

#### Scenario: Request body contains no generation parameters

- **WHEN** the system issues an analysis request
- **THEN** the request body MUST contain exactly the model and the messages
- **AND** the body MUST NOT contain a temperature field
- **AND** the body MUST NOT contain any output length cap field

#### Scenario: Thinking mode remains enabled by provider default

- **WHEN** the configured provider enables thinking mode by default
- **THEN** the system MUST NOT send any field that disables or constrains it
- **AND** the response MUST be accepted when it carries both a reasoning field and an answer field

#### Scenario: Environment template states that no sampling knob exists

- **WHEN** an operator reads the text-role section of the environment template
- **THEN** it MUST state that no temperature or output-cap setting is offered
- **AND** it MUST give the reason: a hardcoded cap truncates long answers into unparseable JSON

### Requirement: Text-role configuration is named for the role, not for a former vendor

The environment variables configuring the text model MUST be named for the role (`TEXT_API_KEY`, `TEXT_BASE_URL`, `TEXT_MODEL`, `TEXT_FALLBACK_MODELS`). The former `GEMINI_*` names MUST continue to be accepted as a fallback source so that an existing deployment does not lose its credential when only some files are updated. When both names carry a value, the role-named one MUST win.

The fallback is retained rather than dropped because losing the credential is a quiet failure: collection still succeeds and every item's analysis fails, so the digest arrives on time looking merely thin rather than broken.

#### Scenario: Role-named variables are read

- **WHEN** `TEXT_API_KEY` and `TEXT_MODEL` are set
- **THEN** the analyzer MUST use those values

#### Scenario: Legacy names still resolve

- **WHEN** only the `GEMINI_*` names are set
- **THEN** the analyzer MUST resolve the same configuration from them

#### Scenario: Both names present

- **WHEN** a role-named variable and its legacy counterpart both carry a value
- **THEN** the role-named value MUST be used

### Requirement: Thinking-mode responses yield the answer text, not the reasoning trace

DeepSeek responses may carry a separate reasoning field alongside the answer content. The system MUST extract only the answer content for downstream parsing and MUST NOT concatenate reasoning text into the analysis result. When the answer content is absent but a reasoning field is present, the system MUST treat the response as unusable rather than substituting the reasoning trace.

#### Scenario: Response carries both reasoning and content

- **WHEN** a response contains a non-empty reasoning field and a non-empty content field
- **THEN** only the content field MUST be returned for JSON parsing

#### Scenario: Response carries reasoning but empty content

- **WHEN** a response contains a reasoning field and an empty content field
- **THEN** the system MUST raise a request failure for that item
- **AND** the reasoning text MUST NOT be stored as the analysis summary

#### Scenario: Response content is a structured part list

- **WHEN** the content field is a list of typed parts rather than a plain string
- **THEN** the text parts MUST be joined and returned as the response text

### Requirement: Provider misconfiguration is visible at startup and in status

The system MUST log the resolved model identifier and endpoint host when the analyzer initializes. Connectivity checks MUST target the configured host. A wrong or expired credential MUST surface as a logged authentication failure for the affected request rather than being reported as an empty analysis.

#### Scenario: Startup log names the active model

- **WHEN** the analyzer initializes with a configured API key
- **THEN** the log line MUST include the resolved model identifier and the endpoint host

#### Scenario: Credential rejected by the provider

- **WHEN** the provider returns an authentication error
- **THEN** the failure MUST be logged with the provider status
- **AND** the affected item MUST record an analysis failure rather than a fabricated summary

#### Scenario: Configured host is unreachable

- **WHEN** the connectivity check to the configured host fails
- **THEN** the analyzer MUST report itself unavailable
- **AND** digest generation MUST proceed with source metadata and without model analysis
