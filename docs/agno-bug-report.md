# Agno Bug Report: Empty List Content Returns "[]" String

## Issue Title
`[fix] get_content_string() returns "[]" for empty content list, causing concatenation issues`

---

## Description

When a model response contains an empty content list `[]` (common after tool execution when the model has nothing more to say), the `Message.get_content_string()` method returns the literal string `"[]"` via `json.dumps([])` instead of returning an empty string.

This string then gets concatenated to existing content in `base.py`, resulting in malformed responses like:

```
"I'll help you execute the command.[]"
```

## Environment

- **Agno Version**: Confirmed in 2.3.21 and 2.3.26
- **Model Provider**: AWS Bedrock (Claude 3.5 Sonnet)
- **Python Version**: 3.13
- **OS**: macOS / Linux

## Steps to Reproduce

```python
from agno.agent import Agent
from agno.models.aws import AwsBedrock
from agno.tools import tool
import aioboto3
import asyncio

@tool(name="run_cmd", description="Run a terminal command")
def run_cmd(command: str) -> str:
    return f"Executed: {command}"

async def main():
    async_session = aioboto3.Session(region_name="us-west-2")
    model = AwsBedrock(
        id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        aws_region="us-west-2",
        async_session=async_session,
    )
    
    agent = Agent(
        model=model,
        tools=[run_cmd],
        instructions="Use the run_cmd tool when asked to execute commands.",
    )
    
    run_output = await agent.arun("Execute: echo hello")
    
    print(f"Content: {repr(run_output.content)}")
    print(f"Content ends with '[]': {run_output.content.endswith('[]')}")

asyncio.run(main())
```

### Expected Output
```
Content: "I'll help you execute the echo command."
Content ends with '[]': False
```

### Actual Output
```
Content: "I'll help you execute the echo command.[]"
Content ends with '[]': True
```

## Root Cause Analysis

### Location 1: `libs/agno/agno/models/message.py` (lines 127-131)

```python
def get_content_string(self) -> str:
    """Returns the content as a string."""
    if isinstance(self.content, str):
        return self.content
    if isinstance(self.content, list):
        if len(self.content) > 0 and isinstance(self.content[0], dict) and "text" in self.content[0]:
            return self.content[0].get("text", "")
        else:
            return json.dumps(self.content)  # BUG: Returns "[]" for empty list!
    return ""
```

When `self.content = []` (empty list):
1. `isinstance(self.content, list)` evaluates to `True`
2. `len(self.content) > 0` evaluates to `False` (empty list)
3. Falls through to `else: return json.dumps(self.content)` which returns `"[]"`

### Location 2: `libs/agno/agno/models/base.py` (line 1117)

```python
if assistant_message.content is not None:
    if model_response.content is None:
        model_response.content = assistant_message.get_content_string()
    else:
        model_response.content += assistant_message.get_content_string()  # Concatenates "[]"
```

### Why Empty List Occurs

After tool execution, if the model has nothing additional to say, AWS Bedrock returns:

```json
{
  "output": {
    "message": {
      "role": "assistant",
      "content": []
    }
  }
}
```

The Bedrock parser in `libs/agno/agno/models/aws/bedrock.py` (lines 698-702) preserves this empty list:

```python
# Extract text content if it's a list of dictionaries
if isinstance(content, list) and content and isinstance(content[0], dict):
    # This condition is False for empty list (content is falsy)
    content = [item.get("text", "") for item in content if "text" in item]
    content = "\n".join(content)

model_response.content = content  # Sets content to [] when list is empty
```

## Suggested Fix

### Option A: Fix in `get_content_string()` (Recommended)

This fix handles all model providers, not just Bedrock:

```python
def get_content_string(self) -> str:
    """Returns the content as a string."""
    if isinstance(self.content, str):
        return self.content
    if isinstance(self.content, list):
        if len(self.content) == 0:
            return ""  # FIX: Return empty string for empty list
        if isinstance(self.content[0], dict) and "text" in self.content[0]:
            return self.content[0].get("text", "")
        else:
            return json.dumps(self.content)
    return ""
```

### Option B: Fix in Bedrock parser

```python
model_response.content = content if content else None
```

## Impact

This bug affects any workflow where:
1. Tools are used
2. The model returns an empty content list after tool execution

The `[]` appears at the end of every such response, which:
- Looks unprofessional in user-facing applications
- May break downstream parsing that expects clean text
- Affects logging and analytics

## Workaround

Until fixed upstream, consumers can strip trailing `[]`:

```python
if text and text.endswith('[]'):
    text = text[:-2]
```

## Related

- Model provider: AWS Bedrock
- Affected components: `Message.get_content_string()`, content concatenation in `base.py`

---

## PR Information

If submitting as a PR, use title format per [CONTRIBUTING.md](https://github.com/agno-agi/agno/blob/v2.0/CONTRIBUTING.md):

**Title**: `[fix] Return empty string for empty content list in get_content_string()`

**Description**: 
```
This PR fixes an issue where `Message.get_content_string()` returns `"[]"` for empty content lists, 
causing malformed responses like `"I'll help you.[]"` after tool execution.

Fixes #<issue_number>

## Changes
- Modified `get_content_string()` in `libs/agno/agno/models/message.py` to return `""` for empty lists
- Added test case to verify empty list handling

## Testing
- Verified with AWS Bedrock + Claude 3.5 Sonnet
- Confirmed `[]` no longer appears in responses after tool execution
```
