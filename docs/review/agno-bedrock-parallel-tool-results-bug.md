# Bug Report: Agno AwsBedrock Splits Parallel Tool Results Into Separate Messages

**Component:** `agno.models.aws.bedrock.AwsBedrock._format_messages()`
**Affected providers:** AWS Bedrock (ConverseStream API)
**Severity:** High — crashes the agent loop whenever the model makes parallel tool calls

---

## Summary

When a model returns multiple `toolUse` blocks in a single assistant message (parallel tool
calls), Agno's `AwsBedrock._format_messages()` emits one separate `user` message per tool
result. The Bedrock ConverseStream API rejects this with a `ValidationException` because it
requires **all tool results for a parallel turn to be in a single user message**.

---

## Steps to Reproduce

1. Use any Agno agent backed by `AwsBedrock` with multiple tools available.
2. Ask something that causes the model to issue two tool calls in one response, e.g.:
   - "list my pods" when `kubectl` is missing — the model may simultaneously run
     `which kubectl` and `docker ps` to diagnose the environment.
3. Observe the `ValidationException` on the next request to Bedrock.

---

## Expected Behaviour

When an assistant message contains N `toolUse` blocks, the following user message must
contain **all N `toolResult` blocks in a single content array**:

```json
[
  {
    "role": "assistant",
    "content": [
      {"toolUse": {"toolUseId": "id-1", "name": "run_shell_command", "input": {...}}},
      {"toolUse": {"toolUseId": "id-2", "name": "run_shell_command", "input": {...}}}
    ]
  },
  {
    "role": "user",
    "content": [
      {"toolResult": {"toolUseId": "id-1", "content": [...]}},
      {"toolResult": {"toolUseId": "id-2", "content": [...]}}
    ]
  }
]
```

---

## Actual Behaviour

Agno's `_format_messages()` splits the results into separate user messages:

```json
[
  {
    "role": "assistant",
    "content": [
      {"toolUse": {"toolUseId": "id-1", ...}},
      {"toolUse": {"toolUseId": "id-2", ...}}
    ]
  },
  {
    "role": "user",
    "content": [{"toolResult": {"toolUseId": "id-1", "content": [...]}}]
  },
  {
    "role": "user",
    "content": [{"toolResult": {"toolUseId": "id-2", "content": [...]}}]
  }
]
```

Bedrock rejects the second request with:

```
ValidationException: An error occurred (ValidationException) when calling the
ConverseStream operation: Expected toolResult blocks at messages.6.content for
the following Ids: tooluse_sFsSpHVEjY6gUi2wkYMIot
```

---

## Root Cause

`AwsBedrock._format_messages()` processes tool results one at a time and appends each as an
independent `user` message without checking whether the preceding assistant turn contained
multiple `toolUse` blocks that should be answered together.

---

## Proposed Fix

After `_format_messages()` produces the message list, merge any consecutive user messages
whose content consists entirely of `toolResult` blocks into a single user message:

```python
@staticmethod
def _merge_parallel_tool_results(
    messages: list[dict],
) -> list[dict]:
    """
    Merge consecutive user messages containing only toolResult blocks into one.

    Required by Bedrock: all toolResult blocks for a parallel assistant turn
    must be in a single user message.
    """
    merged = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        content = msg.get("content", [])
        is_tool_result_msg = (
            msg.get("role") == "user"
            and isinstance(content, list)
            and content
            and all("toolResult" in block for block in content)
        )
        if is_tool_result_msg:
            combined = list(content)
            while i + 1 < len(messages):
                nxt = messages[i + 1]
                nxt_content = nxt.get("content", [])
                if (
                    nxt.get("role") == "user"
                    and isinstance(nxt_content, list)
                    and nxt_content
                    and all("toolResult" in block for block in nxt_content)
                ):
                    combined.extend(nxt_content)
                    i += 1
                else:
                    break
            merged.append({"role": "user", "content": combined})
        else:
            merged.append(msg)
        i += 1
    return merged
```

Call this at the end of `_format_messages()`:

```python
formatted_messages = self._merge_parallel_tool_results(formatted_messages)
return formatted_messages, system_message
```

---

## Workaround (No Longer Needed With the Fix)

Some codebases work around this by injecting a system prompt instruction:

```
IMPORTANT: You must call tools ONE AT A TIME. Never request multiple tool calls
in a single response. Wait for each tool result before calling the next tool.
```

This discourages the model from using parallelism but doesn't fix the underlying formatting
bug and prevents the model from using parallel tool calls efficiently.

---

## References

- [AWS Bedrock ConverseStream API — Tool use](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html)
- Bedrock requirement: *"If the previous response from the model contained tool use content blocks, the user turn should contain tool result content blocks."* (single turn, all results together)
