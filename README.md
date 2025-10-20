# DCAF (DuploCloud Agent Framework)

Build tool-calling agents for DuploCloud Help Desk.

## What's Inside

```
dcaf/
├── llm/
│   └── bedrock.py              # AWS Bedrock Converse API wrapper
├── tools.py                    # Tool creation system (@tool decorator)
├── agents/
│   └── tool_calling_agent.py   # Agent that calls tools and handles approvals
├── schemas/
│   └── messages.py             # Message schemas for Help Desk protocol
└── agent_server.py             # FastAPI server that hosts agents
```

## Quick Start

```python
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool
from dcaf.agent_server import create_chat_app
import uvicorn

# 1. Create tools
@tool(
    schema={
        "name": "get_weather",
        "description": "Get weather for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    requires_approval=False
)
def get_weather(city: str) -> str:
    return f"Weather in {city}: 72°F, sunny"

# 2. Create agent
llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[get_weather],
    system_prompt="You are a helpful assistant."
)

# 3. Create server
app = create_chat_app(agent)

# 4. Run
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Core Components

### 1. BedrockLLM

Calls AWS Bedrock models using the Converse API.

```python
from dcaf.llm import BedrockLLM

llm = BedrockLLM(region_name="us-east-1")

response = llm.invoke(
    messages=[
        {"role": "user", "content": "Hello"}
    ],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=1000,
    tools=[...],  # Optional tool schemas
)

**Configuration Priority:** Explicit `boto3_config` > Environment Variables > Defaults

```python
# 1. With explicit config (full control, overrides everything)
from botocore.config import Config
llm = BedrockLLM(
    boto3_config=Config(read_timeout=60, retries={'max_attempts': 5, 'mode': 'adaptive'})
)

# 2. With environment variables (deployment-time configuration)
# export BOTO3_READ_TIMEOUT=30
# export BOTO3_CONNECT_TIMEOUT=15
# export BOTO3_MAX_ATTEMPTS=5
# export BOTO3_RETRY_MODE=adaptive
llm = BedrockLLM()  # Reads from env vars

# 3. Defaults: read_timeout=20s, connect_timeout=10s, max_attempts=3, mode=standard
llm = BedrockLLM()  # Works out of the box
```

### 2. Tools

Functions the agent can call. Two ways to create them:

**Using @tool decorator:**
```python
from dcaf.tools import tool

@tool(
    schema={
        "name": "delete_file", 
        "description": "Delete a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"}
            },
            "required": ["path"]
        }
    },
    requires_approval=True  # User must approve before execution
)
def delete_file(path: str) -> str:
    # Delete logic here
    return f"Deleted {path}"
```

**Using create_tool:**
```python
from dcaf.tools import create_tool

def multiply(a: int, b: int) -> str:
    return str(a * b)

multiply_tool = create_tool(
    func=multiply,
    schema={
        "name": "multiply",
        "description": "Multiply two numbers", 
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"}
            },
            "required": ["a", "b"]
        }
    }
)
```

**Tools with platform context:**
```python
@tool(
    schema={
        "name": "log_action",
        "description": "Log an action",
        "input_schema": {
            "type": "object", 
            "properties": {
                "action": {"type": "string"}
            },
            "required": ["action"]
        }
    }
)
def log_action(action: str, platform_context: dict) -> str:
    user = platform_context.get("user_id", "unknown")
    return f"User {user} performed: {action}"
```

### 3. ToolCallingAgent

Orchestrates tool calls and handles approvals.

```python
from dcaf.agents import ToolCallingAgent

agent = ToolCallingAgent(
    llm=llm,
    tools=[tool1, tool2, tool3],
    system_prompt="Your instructions here",
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_iterations=10,
    enable_terminal_cmds=True  # Allow terminal command suggestions
)
```

### 4. Agent Server

FastAPI server that hosts your agent.

```python
from dcaf.agent_server import create_chat_app

app = create_chat_app(agent)
# Serves at POST /api/sendMessage
```

## Installation

```bash
# From GitHub
pip install git+https://github.com/duplocloud/service-desk-agents.git

# For development
git clone https://github.com/duplocloud/service-desk-agents.git
cd service-desk-agents
pip install -r requirements.txt
```

## Environment Setup

Create `.env`:
```bash
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-sonnet-20240620-v1:0
```

Or use the credential updater:
```bash
./env_update_aws_creds.sh --tenant=your-tenant
```

## Running Examples

```bash
# Basic agent with tools
python examples/agent_app.py

# Log analysis agent with OpenSearch
python examples/log_analysis_agent.py  

# Tool creation examples
python examples/create_tools.py
```

## Message Protocol

The agent receives and returns structured messages:

**Input:**
```json
{
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"}
  ],
  "platform_context": {
    "tenant_name": "production",
    "user_id": "user123"
  }
}
```

**Output (AgentMessage):**
```python
AgentMessage(
    content="Here's my response",
    data=Data(
        tool_calls=[...],      # Tools needing approval
        executed_tool_calls=[...],  # Already executed tools
        cmds=[...]             # Terminal commands for approval
    )
)
```

## Common Issues

### Tool Schema Validation Error
```
ValidationException: The value at toolConfig.tools.0.toolSpec.inputSchema.json.type must be one of the following: object
```
**Fix:** Ensure your tool schema has this structure:
```python
{
    "name": "tool_name",
    "description": "What it does",
    "input_schema": {  # Must have input_schema
        "type": "object",  # Must be "object"
        "properties": {...},
        "required": [...]
    }
}
```

### Expired AWS Credentials
```
ExpiredTokenException: The security token included in the request is expired
```
**Fix:** Run `./env_update_aws_creds.sh` to refresh credentials.

## Creating Your Own Agent

1. **Simple agent without tools:**
```python
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage

class MyAgent(AgentProtocol):
    def invoke(self, messages):
        user_message = messages["messages"][-1]["content"]
        return AgentMessage(content=f"You said: {user_message}")
```

2. **Agent with tools:**
```python
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool

@tool(schema={...})
def my_tool(param: str) -> str:
    return "result"

agent = ToolCallingAgent(
    llm=llm,
    tools=[my_tool],
    system_prompt="Custom instructions"
)
```

## API Reference

### POST /api/sendMessage

Send messages to the agent.

```bash
curl -X POST http://localhost:8000/api/sendMessage \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is the weather?"}
    ]
  }'
```

## License

See [LICENSE](LICENSE) file.
