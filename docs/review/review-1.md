# DECAF Framework Review Meeting Summary

**Date:** Meeting transcript review  
**Presenter:** Chuck Conway  
**Attendees:** Pranav Chakilam, Andy Boutte, Prem Lakshmanan, Mal Marconi, Sum Yip, Adam Smith

---

## Overview

Chuck presented an expanded version of **DECAF (DuploCloud Agent Framework)**, building on Pranav's original work. The goal is to create a framework that abstracts complexity while allowing agents to focus on solving domain problems. The framework currently uses Agno under the covers but is designed to be swappable.

---

## Key Points & Takeaways

### Philosophy & Design Principles

- **"Hide complexity, expose simplicity"** — but still allow access to advanced controls when needed
- **No vendor lock-in** — abstract implementation details (Agno, LangChain, Strands) so they can be swapped
- **Pranav's strong emphasis on "no magic"** — keep code lean, transparent, and minimal abstractions
  - An agent is fundamentally: one LLM API call + tools. Everything else is noise.
  - As few lines of code and as few abstractions as possible
  - Complete transparency — no one should wonder "what is this? how does it work?"
- **Target audience:** internal engineers now, but eventually **customers** building their own agents

### New Features Added

| Feature | Description |
|---------|-------------|
| **Tool calling** | With approval workflows |
| **Human-in-the-loop** | Approval process for high-risk operations |
| **Session state management** | Persist data between conversation turns |
| **Streaming support** | Real-time response streaming |
| **REST API changes** | Renamed endpoints, snake_case convention |
| **Request/Response interceptors** | Modify payloads before/after LLM calls |
| **Event system** | Pub/sub pattern for logging, notifications |
| **Prompt caching** | Cache static portions of prompts for cost/speed savings (experimental) |

### Tool Definition Methods

Three ways to define tool schemas:

1. **Auto-generated** — from function signature (simplest)
2. **Dictionary schema** — most flexible, least safe
3. **Pydantic models** — most structured, validates at definition time

### Modules DuploCloud Should Fully Own

Per team agreement, these should NOT be delegated to Agno:

1. **Schemas module** — Pydantic data classes for API inputs/outputs
2. **Agent server module** — FastAPI app creation and endpoints

### Key Agreements Reached

| Decision | Details |
|----------|---------|
| High-risk tools flag location | Should live on the tool itself via decorator (`requires_approval=True`), not passed separately to agent |
| Schema ownership | Schemas and agent server modules fully owned by DuploCloud |
| REST endpoint naming | Lowercase snake_case (`/chat` instead of `/sendMessage`) |
| Type safety | Use Pydantic models wherever possible |

---

## Questions Asked

### Pranav Chakilam

1. Can we go to the slide with all the agent inputs (high-risk tools, system prompt, etc.)?
2. Why is `high_risk_tools` a separate agent parameter instead of an attribute on the tool itself?
3. What is the input/output of request interceptors? Is it the raw JSON body sent to the LLM API?
4. Can we reuse existing schema classes (e.g., `AgentMessage`) instead of creating new ones like `AgentResult`?
5. Does the `serve()` function contain custom logic or reuse existing code?
6. Are we moving to a stateful session pattern where the agent maintains internal state (like LangChain)?
7. How do we invoke the agent? Can we pass in the entire messages array?
8. How is platform context (kubeconfig, Duplo token) passed to tools without exposing it to the LLM?
9. Does Agno let us log the time taken by an LLM API call and the request body sent?

### Prem Lakshmanan

1. Are the request interceptors and response interceptors from Agno, or custom additions?
2. There are places using Pydantic models and places using dictionaries — is this intentional?
3. The session object goes to AI Help Desk and back — how does this workflow function?
4. What happens with dynamic prompts for caching (values injected at runtime)?
5. Is platform context sent to the LLM? (Concern about sensitive data like kubeconfig)
6. Can we generate PyDocs/documentation from the code?

### Andy Boutte

1. Did you claim "decaf" on PyPI? (To Pranav)
2. Regarding high-risk tools — shouldn't this be more granular than true/false? (e.g., regex patterns, approval checker functions)
3. The interceptors are a decaf engineering responsibility to place hooks — am I thinking about that correctly?
4. The interceptor feature is great — should we commit it upstream to Agno?
5. So system context is just prompt organization to maximize cache hits?
6. Prompt caching increased performance but also cost? Or decreased cost?

### Adam Smith

1. When is the test? When can I feed it into the robot?

---

## Actionable Items

### Must Address

| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Move `high_risk_tools` to tool decorator (`requires_approval=True`) | Chuck | Open | Pranav's suggestion — team agreed |
| Review `AgentResult` vs existing `AgentMessage` schema | Chuck | Open | Determine if they can be unified |
| Clarify how messages/thread history is passed to agent | Chuck | Open | Pranav asked — Chuck to investigate |
| Verify platform context is NOT sent to LLM | Chuck | Open | Prem's security concern |
| Confirm how platform context is injected into tools | Chuck | Open | Explain the wrapper/currying mechanism |
| Test prompt caching implementation | Chuck | Open | Currently experimental |
| Claim "decaf" on PyPI | Pranav | Open | Andy's suggestion to avoid naming conflicts |

### Design Considerations

| Item | Notes |
|------|-------|
| Interceptor granularity | Add more hooks over time: before/after tool call, before response flows back, etc. |
| High-risk tool approval | Make it more granular — support regex patterns, approval checker functions (Andy's suggestion) |
| `serve()` abstraction debate | Pranav prefers explicit UVicorn code (transparency); Chuck prefers abstraction (simplicity for customers). **Decision:** see how it evolves |
| Session naming | Pranav suggests "session" may be confusing — consider "turn_data" or similar |
| Logging from Agno | Verify what Agno logs (timing, request bodies) |

### Future Work

- [ ] Add more interceptor hooks as use cases emerge
- [ ] Consider upstream contribution of interceptor feature to Agno
- [ ] Generate public documentation (MKDocs/PyDocs) for customer consumption
- [ ] Test streaming functionality end-to-end
- [ ] Evaluate prompt caching cost/benefit on real agents

---

## Technical Deep Dives

### Session State Management

**Problem:** Data retrieved during a conversation (e.g., tenant info from Neo4j) must be re-fetched on every turn.

**Solution:** Session storage that persists data across conversation turns.

**Example use case (Architecture Diagram Agent):**
1. User asks to diagram all pods
2. Agent queries database, generates diagram
3. User asks to add Docker image versions
4. **Without sessions:** Re-query database
5. **With sessions:** Use cached data, regenerate immediately

**Current implementation:** Uses the `data` attribute in Help Desk responses (server-side storage, transmitted back and forth).

**Future options:** Redis, file storage, database — swappable via interface.

### Prompt Caching

**How it works:**
- Cache static portions of prompts (instructions, examples)
- Only dynamic content (user input, context) is reprocessed

**Bedrock specifics:**
- 4 checkpoints available
- Cache expires after 5 minutes of inactivity
- Minimum 1,000 tokens required

**Cost implications:**
| Operation | Cost |
|-----------|------|
| First write (cache creation) | ~25% MORE expensive |
| Subsequent reads (cache hits) | ~90% CHEAPER, up to 50% faster |

**Best candidates:** Agents with large static prompts and multi-turn conversations (e.g., Architecture Diagram Agent where ~90-95% of prompt is static).

### Platform Context & Tool Security

**Concern:** Sensitive data (kubeconfig, Duplo tokens) should NOT be sent to the LLM.

**Solution:** Platform context is injected into tools via function wrapping (currying/`functools.partial` pattern).

- LLM only sees the tool schema with required parameters (e.g., `cipher`, `params`)
- Platform context is pre-bound to the function before LLM invocation
- Tool receives context at execution time without LLM involvement

---

## Notable Quotes

> **Pranav:** "An agent, at the end of the day, is one LLM API call and two functions. Everything else is noise."

> **Chuck:** "We want to do the most with the least — most work done, least amount of abstraction."

> **Andy:** "We have very low expectations that a customer is gonna build agents end-to-end by themselves [in the short term], but that's absolutely the direction we want things to go."

> **Pranav:** "We should try to not have as few lines as possible in the framework, because it can easily become bloated, and then it'll become spaghetti."

---

## Appendix: Framework Architecture

### Agent Parameters

```python
Agent(
    tools=[...],                    # List of tool functions
    system_prompt="...",            # Static instructions
    model="...",                    # Model identifier
    provider="...",                 # LLM provider (Anthropic, OpenAI, etc.)
    high_risk_tools=[...],          # DEPRECATED: Move to tool decorator
    on_event=callback,              # Event handler for logging, etc.
    request_interceptors=[...],     # Modify requests before LLM
    response_interceptors=[...]     # Modify responses after LLM
)
```

### Serve Method

```python
serve(
    agent=agent,      # Agent instance or callable returning AgentResult
    port=8000,        # Server port
    host="0.0.0.0",   # Server host
    workers=4,        # UVicorn worker count
    timeout=30,       # Request timeout
    log_level="info"  # Logging verbosity
)
```

### Tool Definition with Approval

```python
@tool(
    description="Execute kubectl command",
    requires_approval=True  # Triggers human-in-the-loop
)
def execute_kubectl(command: str, platform_context: PlatformContext):
    # Platform context injected via wrapper, not by LLM
    ...
```

---

## Next Steps

1. Chuck to address outstanding questions and update design
2. Team code review once implementation hardens
3. Test with existing agents (Architecture Diagram, Kubernetes)
4. Documentation for internal and eventual customer use