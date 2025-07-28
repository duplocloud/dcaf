# LLM Framework Abstraction – Feature Specification

> **Status**: Draft – v0.1 (2025-06-29)

This document describes the architecture and concrete features required to realise the goals outlined in the *Gap Analysis*. It is intentionally implementation-agnostic and should serve as the canonical reference for contributors.

---

## Guiding Principles
1. **Opaque Frameworks** – Down-stream consumers must not depend on LangChain, FastAPI, Anthropic SDKs, etc.
2. **Pluggability** – Swap any major subsystem (LLM provider, prompt store, MCP transport) by changing configuration.
3. **Explicit Contracts** – Typed, well-documented protocols act as seams; both internal and external.
4. **Single Source of Truth** – Prompts, tool schemas, and configuration are centrally managed.
5. **Security by Default** – All provider credentials flow through Pydantic settings; no hard-coded secrets.

---

## High-Level Architecture

```mermaid
flowchart TD
  subgraph "Application Boundary"
    main["main.py\n(entry point)"] --invokes--> chatSvc["ChatService"]
  end

  chatSvc --uses--> agentCore[Agent]
  agentCore --depends--> llmClient[LLMClient (interface)]
  agentCore --depends--> toolMgr[ToolManager]
  agentCore --depends--> promptProv[PromptProvider]
  agentCore --depends--> respFmt[ResponseFormatter]

  llmClient --implements--> bedrock[BEdrockAdapter]
  llmClient --implements--> anthropic[AnthropicAdapter]
  llmClient --implements--> openai[OpenAIAdapter]
  toolMgr --executes--> shell[CommandRunner]
  toolMgr --executes--> mcp[MCPAdapter]
```

*(Arrows indicate "depends on" relations; dotted boxes are pluggable implementations.)*

---

## Core Interfaces

### 1. LLMClient (`src/llm/base.py`)
```
class LLMClient(Protocol):
    """Provider-agnostic interface used by all agents."""

    def invoke(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list[ToolSchema] | None = None,
        tool_choice: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...
```
*Return value* is a dataclass capturing raw provider payload + normalised content.

### 2. PromptProvider (`src/prompts/provider.py`)
```
class PromptProvider(Protocol):
    def get(self, name: str, **params) -> str: ...
```
Implementations:
* `FileSystemPromptProvider` – YAML/JSON/MD templates under `prompts/`.
* `DBPromptProvider` – RDS/Dynamo/etc.

### 3. ResponseFormatter (`src/llm/formatters.py`)
```
class ResponseFormatter(Protocol):
    def format(self, raw_response: LLMResponse) -> str | dict[str, Any]: ...
```
Built-ins:
* `JsonFormatter` – guarantees valid JSON.
* `MarkdownFormatter` – strips code fences.
* `PassthroughFormatter` – returns raw text.

### 4. Tool Abstractions
* `Tool` – metadata + callable.
* `ToolSchema` – JSON schema published to LLM.
* `ToolManager` – registry + execution + approval workflow.
* `CommandRunner` – executes shell commands safely (non-interactive, timeout, capture output).

### 5. MCPAdapter
Adapter that maps our `Message` schema ↔ MCP JSON so any MCP-compliant runtime can be leveraged.

---

## Configuration Extensions (`src/config.py`)
```toml
[llm]
provider = "bedrock"            # bedrock | anthropic | openai
model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"

[prompts]
store = "filesystem"            # filesystem | db | http
path = "./prompts"
```
*Settings* object instantiates concrete classes via a small factory in `src/registry.py`.

---

## Execution Flow (Happy Path)
1. `python main.py` bootstraps settings & logging, creates `ChatService` instance.
2. `ChatService` receives HTTP request (still FastAPI internally) → converts into internal `Messages` model.
3. `Agent` decides on tools / prompts → calls `LLMClient.invoke()`.
4. `BedrockAdapter` performs request; raw response fed through `ResponseFormatter`.
5. If `tool_use` detected, `ToolManager` validates & (a) executes non-approval tools, (b) emits approval requests back.
6. Final `AgentMessage` returned to `ChatService`, serialised to API response.

---

## Phased Implementation Plan
| Phase | Scope | Success Metric |
|-------|-------|----------------|
| 0 | **Stabilise tests & CI** – back-fill coverage for existing agents, ensure green build. | ≥80 % coverage baseline |
| 1 | Introduce `LLMClient` ABC + migrate `BedrockAnthropicLLM` to implement it. | All agents depend on interface, not concrete class |
| 2 | Extract `ToolManager`; refactor `ToolCallingBoilerplateAgent`. | No tool-related code inside agents except high-level orchestration |
| 3 | Add `PromptProvider` + YAML prompt store; migrate hard-coded prompts. | Prompts editable without touching code |
| 4 | Implement `ResponseFormatter` strategies; update `LLMClient.invoke` to accept formatter injection. | JSON answers parse 100 % of the time |
| 5 | MCPAdapter integration; demo with alternative MCP-capable library. | Echo agent works via MCP path |
| 6 | Add second provider adapter (Anthropic direct API) and switch via env var. | Passing e2e tests for both providers |

---

## Non-Goals (v1)
* **UI/Frontend changes** – handled by separate team.
* **Agent reasoning improvements** – will naturally evolve but not target of abstraction work.
* **Database prompt store** – out-of-scope until filesystem store proves insufficient.

---

## Open Questions
1. Which MCP library will we standardise on? (E.g. `mcp-python`, `duplo-mcp`?)
2. Do we require per-provider streaming support v1, or can we fallback to blocking calls?
3. Should `ToolManager` live inside server process only, or be shareable as client-side library?

Feedback welcome – please comment inline or open an issue referencing this spec. 