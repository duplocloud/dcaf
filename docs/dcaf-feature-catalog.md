# DCAF Feature Catalog & Future Roadmap

## Current Features

### 1. Core Architecture — Hexagonal / Ports & Adapters

DCAF follows a clean hexagonal architecture with clear separation between domain logic, application services, and infrastructure adapters.

- **Domain layer** (`dcaf/core/domain/`) — `Session`, `AgentResponse`, `ToolCall`, `ApprovalStatus` value objects
- **Application services** (`dcaf/core/application/services/`) — `AgentService` orchestrates agent execution
- **Ports (interfaces)** (`dcaf/core/application/ports/`) — `LLMPort`, `ToolExecutorPort` define contracts
- **Adapters** (`dcaf/core/adapters/`) — Inbound (HTTP server) and outbound (LLM providers) implementations

### 2. Agent System

- **`Agent` class** (`dcaf/core/agent.py`) — Main entry point. Configurable with `provider`, `model`, `tools`, `system_prompt`, `instructions`, `temperature`, `max_tokens`, `max_turns`
- **`agent.run()`** — Single-shot invocation with message history + context
- **`agent.run_stream()`** — Token-level streaming invocation
- **Provider support** — Amazon Bedrock (via Agno adapter), with architecture ready for additional providers
- **Legacy agents** (`dcaf/agents/`) — Pre-existing `AwsAgent`, `K8sAgent`, `CmdAgent` with a `BaseCommandAgent` mixin pattern and backward-compatible boilerplate

### 3. Tool System

- **MCP (Model Context Protocol) tools** (`dcaf/core/tools/mcp.py`) — First-class MCP server integration via `MCPTools` class supporting `stdio` and `sse` transport types
- **Tool configuration via YAML** — Tools declared in `dcaf.yaml` with server name, command, args, env vars, and URL
- **`exclude_tools`** — Glob pattern support (`fnmatch`) to selectively exclude tools from MCP servers
- **Headers support** — HTTP headers configurable per MCP server for auth
- **`ToolExecutorPort`** — Clean interface for tool execution, with the Agno adapter handling actual execution

### 4. Human-in-the-Loop Tool Approval

- **Approval policies** (`dcaf/core/domain/approval_policy.py`) — `AlwaysApprove`, `AlwaysDeny`, `AutoApproveList` (with glob pattern matching)
- **`ApprovalService`** (`dcaf/core/application/services/approval_service.py`) — Evaluates tool calls against policies, manages pending approvals
- **`ApprovalStatus` enum** — `APPROVED`, `DENIED`, `PENDING`
- **Session-integrated** — Pending tool calls stored in session, returned to client for approval, then re-submitted
- **`ServerAdapter`** processes approved tool calls — Extracts `_approved_tool_calls` and `_denied_tool_calls` from message metadata
- **Configurable via `dcaf.yaml`** — `approval_policy` field with `type` and `auto_approve_tools` list

### 5. Session Management

- **`Session` domain object** (`dcaf/core/domain/session.py`) — Tracks conversation messages, tool calls, pending approvals
- **`SessionService`** (`dcaf/core/application/services/session_service.py`) — Creates/manages sessions
- **Agentic loop tracking** — `max_turns` limits on agent execution to prevent runaway tool-calling loops
- **Platform context** — Sessions carry platform-specific context (e.g., `source`, `channel`) extracted from messages

### 6. Streaming

- **Token-level streaming** — `agent.run_stream()` yields `StreamEvent` objects
- **Event types**:
  - `TextDeltaEvent` — Individual token chunks
  - `ToolCallEvent` — Tool invocation notifications
  - `ToolResultEvent` — Tool execution results
  - `DoneEvent` — Stream completion signal
  - `ErrorEvent` — Error during streaming
  - `ApprovalRequestEvent` — Tool needs human approval
- **NDJSON over HTTP** — `/api/chat-stream` endpoint returns `application/x-ndjson`

### 7. Server / API Layer

- **`create_app()`** (`dcaf/core/server.py`) — Creates a FastAPI application from an `Agent` or callable
- **`serve()`** — Convenience method to create and run with uvicorn
- **Endpoints**:
  - `GET /health` — Health check
  - `POST /api/chat` — Synchronous chat
  - `POST /api/chat-stream` — Streaming chat (NDJSON)
- **`AgentProtocol`** (`dcaf/agent_server.py`) — Runtime-checkable protocol for pluggable agents
- **`additional_routers`** — Users can mount custom FastAPI routers alongside the agent
- **Callable agents** — Supports raw functions as agents via `CallableAdapter`

### 8. A2A (Agent-to-Agent Protocol)

- **A2A support** (`dcaf/core/a2a/`) — Google's Agent-to-Agent protocol integration
- **Agent Card** — `/.well-known/agent.json` endpoint exposing agent capabilities
- **A2A task endpoints** — `/a2a/tasks/send`, `/a2a/tasks/sendSubscribe`, `/a2a/tasks/get`, `/a2a/tasks/cancel`
- **Agno adapter** (`dcaf/core/adapters/outbound/agno/a2a_adapter.py`) — Bridges DCAF agents to A2A protocol
- **Configurable** — Enabled via `a2a=True` parameter on `create_app()`

### 9. Configuration System

- **`dcaf.yaml`** (`dcaf/core/config.py`) — Central YAML configuration file
- **Hierarchical config** — `provider`, `model`, `system_prompt`, `instructions`, `temperature`, `max_tokens`, `tools` (MCP servers), `approval_policy`, `a2a`
- **Environment variable support** — Providers use standard AWS env vars; MCP servers can pass env vars
- **`DcafConfig` Pydantic model** — Typed, validated configuration with defaults
- **Auto-discovery** — Looks for `dcaf.yaml` in the current directory

### 10. Interceptors / Middleware

- **`Interceptor` base class** (`dcaf/core/application/interceptors.py`) — Pre/post processing hooks on agent execution
- **`before_run()`** — Modify messages/context before LLM call
- **`after_run()`** — Modify response after LLM call
- **Registered on `Agent`** — `agent.add_interceptor(interceptor)`
- **Use cases** — Logging, metrics, content filtering, context injection

### 11. Channel Routing

- **`ChannelResponseRouter`** (`dcaf/channel_routing.py`) — Determines whether the agent should respond based on message source
- **Slack integration** — Checks message source and can decide whether agent should respond (e.g., only respond when @mentioned)

### 12. CLI

- **`dcaf` CLI** (`dcaf/cli.py`) — Command-line interface
- **`dcaf serve`** — Start the agent server from a `dcaf.yaml` config

### 13. Testing Utilities

- **`dcaf.core.testing` module** (`dcaf/core/testing/`):
  - **`FakeLLM`** (`fakes.py`) — In-memory LLM replacement for tests, configurable responses
  - **`AgentBuilder`** (`builders.py`) — Fluent builder for constructing test agents
  - **`fixtures.py`** — Pytest fixtures for common test scenarios
- **367 tests** across the full feature set

### 14. Prompt Caching

- **Prompt caching support** (`dcaf/core/adapters/outbound/agno/adapter.py`) — Leverages Bedrock/Anthropic prompt caching for system prompts
- **Automatic cache point injection** — System messages marked with cache control hints to reduce token costs on repeated calls

---

## Suggested Future Features

### Near-term (builds on existing foundations)

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Multi-provider support** | The `LLMPort` abstraction is already in place but only Bedrock/Agno is implemented. Adding OpenAI, Azure OpenAI, and Google Vertex adapters would significantly broaden adoption. |
| 2 | **Persistent session storage** | Sessions are currently in-memory. Adding a `SessionRepositoryPort` with Redis/DynamoDB/PostgreSQL implementations would enable stateful multi-turn conversations across restarts and horizontal scaling. |
| 3 | **Observability & tracing** | The interceptor system is a natural fit for OpenTelemetry integration: trace spans per agent turn, tool call latency, token usage metrics, and LLM cost tracking. |
| 4 | **Tool result caching** | Cache deterministic tool results (e.g., API lookups, database queries) to avoid redundant calls during multi-turn conversations. The tool executor port could be wrapped with a caching layer. |
| 5 | **Guardrails / content filtering interceptor** | A built-in interceptor for input/output content safety (PII detection, topic restrictions, output format enforcement). The interceptor system already supports this pattern. |

### Medium-term (new capabilities)

| # | Feature | Description |
|---|---------|-------------|
| 6 | **Multi-agent orchestration** | A2A is there for inter-service communication, but a local orchestrator that coordinates multiple agents (e.g., planner → researcher → writer) with shared context would enable complex workflows without network overhead. |
| 7 | **Webhook / async callback delivery** | For long-running tool executions, allow the server to accept a callback URL, return immediately with a task ID, and POST results when done. This pairs well with the existing A2A task model. |
| 8 | **Agent memory / RAG integration** | A `MemoryPort` for long-term agent memory (vector store integration) that persists across sessions. Agents could remember user preferences, past decisions, and domain knowledge. |
| 9 | **Rate limiting & quota management** | Per-user or per-tenant rate limits on the API layer, plus token budget enforcement at the agent level to control LLM costs. |
| 10 | **Authentication & multi-tenancy** | JWT/OAuth middleware on the API endpoints with tenant-scoped configuration (different tools, models, and approval policies per tenant). |

### Longer-term (strategic)

| # | Feature | Description |
|---|---------|-------------|
| 11 | **Visual workflow builder / agent graph DSL** | A declarative way to compose multi-step agent workflows (YAML or visual), where each node is an agent or tool with conditional branching, parallel execution, and error handling. |
| 12 | **Evaluation & benchmarking framework** | Automated testing of agent quality: define expected outcomes for test conversations, measure tool selection accuracy, response quality scores, and regression detection across model/prompt changes. |
| 13 | **Plugin marketplace / tool registry** | A registry of pre-built MCP tool packages (e.g., "Jira tools", "AWS tools", "Slack tools") that can be installed into a DCAF agent with a single config line. |
| 14 | **Federated agent discovery** | Extend A2A with a service registry so agents can discover and negotiate capabilities with each other dynamically, rather than being hard-wired. |
