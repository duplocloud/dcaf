# API Reference (Legacy)

!!! warning "Legacy API"
    This documents the **v1 API**. For new projects, use the [Core API](../core/index.md).
    
    See [Migration Guide](../guides/migration.md) to upgrade existing code.

This section provides detailed API documentation for all DCAF v1 components.

## Components

| Component | Description |
|-----------|-------------|
| [BedrockLLM](./llm.md) | AWS Bedrock Converse API wrapper for model invocation |
| [Tools](./tools.md) | Tool creation system with `@tool` decorator and approval workflows |
| [Agents](./agents.md) | Pre-built agent classes and the `AgentProtocol` interface |
| [Agent Server](./agent-server.md) | FastAPI server for hosting agents |
| [Schemas](./schemas.md) | Message schemas for the Help Desk protocol |
| [Channel Routing](./channel-routing.md) | Slack and channel-specific response routing |
| [CLI](./cli.md) | Command-line tools for credential management |

## Quick Links

### Creating Tools

```python
from dcaf.tools import tool

@tool(
    schema={
        "name": "my_tool",
        "description": "Does something useful",
        "input_schema": {
            "type": "object",
            "properties": {
                "param": {"type": "string"}
            }
        }
    },
    requires_approval=True
)
def my_tool(param: str) -> str:
    return f"Result: {param}"
```

### Creating Agents

```python
from dcaf.agents import ToolCallingAgent
from dcaf.llm import BedrockLLM

llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[my_tool],
    system_prompt="You are a helpful assistant.",
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0"
)
```

### Serving Agents

```python
from dcaf.agent_server import create_chat_app
import uvicorn

app = create_chat_app(agent)
uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Core API Reference

For the Core architecture with Clean Architecture, see:

- [Core Overview](../core/index.md)
- [Domain Layer](../core/domain.md)
- [Application Layer](../core/application.md)
- [Adapters](../core/adapters.md)

