# Streaming Guide

This guide covers how to use streaming responses in DCAF for real-time, incremental updates from agents.

---

## Table of Contents

1. [Overview](#overview)
2. [Stream Event Types](#stream-event-types)
3. [Server-Side Streaming](#server-side-streaming)
4. [Client-Side Consumption](#client-side-consumption)
5. [Error Handling](#error-handling)
6. [Best Practices](#best-practices)

---

## Overview

DCAF supports streaming responses through the `/api/sendMessageStream` endpoint. Streaming provides:

- **Real-time updates** as the LLM generates tokens
- **Progressive UI** updates for better user experience
- **Tool execution visibility** before completion
- **Early termination** capability

### Streaming Format

DCAF uses **NDJSON** (Newline-Delimited JSON) for streaming:

```
{"type":"text_delta","text":"Hello"}
{"type":"text_delta","text":" there!"}
{"type":"done","stop_reason":"end_turn"}
```

Each line is a complete JSON object that can be parsed independently.

---

## Stream Event Types

DCAF supports 7 event types:

### 1. text_delta

Streaming text tokens from the LLM.

```json
{
    "type": "text_delta",
    "text": "Hello"
}
```

**Use:** Append `text` to the displayed response.

### 2. tool_calls

Tool calls requiring user approval.

```json
{
    "type": "tool_calls",
    "tool_calls": [
        {
            "id": "toolu_123",
            "name": "delete_file",
            "input": {"path": "/tmp/file.txt"},
            "execute": false,
            "tool_description": "Delete a file",
            "input_description": {...}
        }
    ]
}
```

**Use:** Display approval UI for tools.

### 3. executed_tool_calls

Tools that were executed automatically.

```json
{
    "type": "executed_tool_calls",
    "executed_tool_calls": [
        {
            "id": "toolu_456",
            "name": "get_status",
            "input": {"service": "web-app"},
            "output": "Service is running"
        }
    ]
}
```

**Use:** Display executed tool information.

### 4. commands

Terminal commands for approval.

```json
{
    "type": "commands",
    "commands": [
        {
            "command": "kubectl get pods -n production",
            "execute": false,
            "files": null
        }
    ]
}
```

**Use:** Display command approval UI.

### 5. executed_commands

Commands that were executed.

```json
{
    "type": "executed_commands",
    "executed_cmds": [
        {
            "command": "kubectl get pods",
            "output": "NAME        READY   STATUS\nweb-123   1/1     Running"
        }
    ]
}
```

**Use:** Display command output.

### 6. done

Stream completed successfully.

```json
{
    "type": "done",
    "stop_reason": "end_turn"
}
```

**Stop reasons:**
- `end_turn` - Normal completion
- `tool_use` - Stopped for tool execution
- `max_tokens` - Token limit reached

**Use:** Finalize UI, enable user input.

### 7. error

Error during streaming.

```json
{
    "type": "error",
    "error": "Connection timeout"
}
```

**Use:** Display error message, offer retry.

---

## Server-Side Streaming

### Agent with Streaming Support

Agents that support streaming implement `invoke_stream`:

```python
from dcaf.schemas.events import (
    TextDeltaEvent, 
    ToolCallsEvent,
    ExecutedToolCallsEvent,
    DoneEvent, 
    ErrorEvent
)
from typing import Generator

class StreamingAgent:
    def invoke_stream(
        self, 
        messages: dict
    ) -> Generator:
        """Stream response events."""
        try:
            # Stream text deltas
            for chunk in self._generate_response(messages):
                yield TextDeltaEvent(text=chunk)
            
            # Check for tool calls
            if self.pending_tool_calls:
                yield ToolCallsEvent(tool_calls=self.pending_tool_calls)
            
            # Yield done event
            yield DoneEvent(stop_reason="end_turn")
            
        except Exception as e:
            yield ErrorEvent(error=str(e))
```

### Using BedrockLLM Streaming

```python
from dcaf.llm import BedrockLLM
from dcaf.schemas.events import TextDeltaEvent, DoneEvent

llm = BedrockLLM()

def stream_response(messages):
    for event in llm.invoke_stream(
        messages=messages,
        model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
        max_tokens=1000
    ):
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                yield TextDeltaEvent(text=delta["text"])
        
        elif "messageStop" in event:
            reason = event["messageStop"].get("stopReason", "end_turn")
            yield DoneEvent(stop_reason=reason)
```

---

## Client-Side Consumption

### Python Client

```python
import requests
import json

def stream_chat(messages: list):
    """Stream responses from the agent."""
    response = requests.post(
        "http://localhost:8000/api/sendMessageStream",
        json={"messages": messages},
        stream=True
    )
    
    accumulated_text = ""
    
    for line in response.iter_lines():
        if line:
            event = json.loads(line.decode('utf-8'))
            event_type = event.get("type")
            
            if event_type == "text_delta":
                text = event.get("text", "")
                accumulated_text += text
                print(text, end="", flush=True)
            
            elif event_type == "tool_calls":
                print("\n[Tool calls pending approval]")
                for tc in event.get("tool_calls", []):
                    print(f"  - {tc['name']}: {tc['input']}")
            
            elif event_type == "executed_tool_calls":
                for etc in event.get("executed_tool_calls", []):
                    print(f"\n[Executed: {etc['name']}]")
                    print(f"  Output: {etc['output']}")
            
            elif event_type == "commands":
                print("\n[Commands pending approval]")
                for cmd in event.get("commands", []):
                    print(f"  $ {cmd['command']}")
            
            elif event_type == "executed_commands":
                for cmd in event.get("executed_cmds", []):
                    print(f"\n[Executed: {cmd['command']}]")
                    print(f"  Output: {cmd['output']}")
            
            elif event_type == "done":
                print(f"\n[Done: {event.get('stop_reason')}]")
                return accumulated_text
            
            elif event_type == "error":
                print(f"\n[Error: {event.get('error')}]")
                raise Exception(event.get("error"))
    
    return accumulated_text

# Usage
result = stream_chat([
    {"role": "user", "content": "Tell me about Kubernetes"}
])
```

### JavaScript/TypeScript Client

```javascript
async function streamChat(messages) {
    const response = await fetch('/api/sendMessageStream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages })
    });
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    let accumulatedText = '';
    let buffer = '';
    
    while (true) {
        const { value, done } = await reader.read();
        
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        // Process complete lines
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete line in buffer
        
        for (const line of lines) {
            if (!line.trim()) continue;
            
            try {
                const event = JSON.parse(line);
                
                switch (event.type) {
                    case 'text_delta':
                        accumulatedText += event.text;
                        updateDisplay(event.text);
                        break;
                    
                    case 'tool_calls':
                        showToolApproval(event.tool_calls);
                        break;
                    
                    case 'executed_tool_calls':
                        showExecutedTools(event.executed_tool_calls);
                        break;
                    
                    case 'commands':
                        showCommandApproval(event.commands);
                        break;
                    
                    case 'executed_commands':
                        showExecutedCommands(event.executed_cmds);
                        break;
                    
                    case 'done':
                        finalize(event.stop_reason);
                        return accumulatedText;
                    
                    case 'error':
                        handleError(event.error);
                        throw new Error(event.error);
                }
            } catch (e) {
                console.error('Parse error:', e);
            }
        }
    }
    
    return accumulatedText;
}

function updateDisplay(text) {
    const display = document.getElementById('response');
    display.textContent += text;
}

function showToolApproval(toolCalls) {
    // Render tool approval UI
    for (const tc of toolCalls) {
        console.log(`Tool: ${tc.name}`, tc.input);
    }
}
```

### React Hook

```jsx
import { useState, useCallback } from 'react';

function useStreamingChat() {
    const [text, setText] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [toolCalls, setToolCalls] = useState([]);
    const [error, setError] = useState(null);
    
    const sendMessage = useCallback(async (messages) => {
        setText('');
        setToolCalls([]);
        setError(null);
        setIsStreaming(true);
        
        try {
            const response = await fetch('/api/sendMessageStream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages })
            });
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            let buffer = '';
            
            while (true) {
                const { value, done } = await reader.read();
                
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                
                for (const line of lines) {
                    if (!line.trim()) continue;
                    
                    const event = JSON.parse(line);
                    
                    switch (event.type) {
                        case 'text_delta':
                            setText(prev => prev + event.text);
                            break;
                        case 'tool_calls':
                            setToolCalls(event.tool_calls);
                            break;
                        case 'error':
                            setError(event.error);
                            break;
                    }
                }
            }
        } catch (e) {
            setError(e.message);
        } finally {
            setIsStreaming(false);
        }
    }, []);
    
    return { text, isStreaming, toolCalls, error, sendMessage };
}

// Usage in component
function ChatComponent() {
    const { text, isStreaming, toolCalls, error, sendMessage } = useStreamingChat();
    const [input, setInput] = useState('');
    
    const handleSubmit = () => {
        sendMessage([{ role: 'user', content: input }]);
        setInput('');
    };
    
    return (
        <div>
            <div className="response">
                {text}
                {isStreaming && <span className="cursor">▌</span>}
            </div>
            
            {toolCalls.length > 0 && (
                <div className="tool-calls">
                    {toolCalls.map(tc => (
                        <ToolApproval key={tc.id} toolCall={tc} />
                    ))}
                </div>
            )}
            
            {error && <div className="error">{error}</div>}
            
            <input
                value={input}
                onChange={e => setInput(e.target.value)}
                disabled={isStreaming}
            />
            <button onClick={handleSubmit} disabled={isStreaming}>
                Send
            </button>
        </div>
    );
}
```

### cURL

```bash
# Stream response
curl -N -X POST http://localhost:8000/api/sendMessageStream \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Tell me a story"}]}'

# Output (each line is a separate event):
# {"type":"text_delta","text":"Once"}
# {"type":"text_delta","text":" upon"}
# {"type":"text_delta","text":" a"}
# {"type":"text_delta","text":" time"}
# ...
# {"type":"done","stop_reason":"end_turn"}
```

---

## Error Handling

### Client-Side Error Handling

```python
import requests
import json

def safe_stream_chat(messages):
    """Stream with comprehensive error handling."""
    try:
        response = requests.post(
            "http://localhost:8000/api/sendMessageStream",
            json={"messages": messages},
            stream=True,
            timeout=60
        )
        response.raise_for_status()
        
        for line in response.iter_lines():
            if not line:
                continue
            
            try:
                event = json.loads(line.decode('utf-8'))
            except json.JSONDecodeError as e:
                print(f"JSON parse error: {e}")
                continue
            
            event_type = event.get("type")
            
            if event_type == "error":
                error_msg = event.get("error", "Unknown error")
                raise StreamError(error_msg)
            
            elif event_type == "text_delta":
                yield event.get("text", "")
            
            elif event_type == "done":
                return
    
    except requests.exceptions.Timeout:
        raise StreamError("Request timed out")
    
    except requests.exceptions.ConnectionError:
        raise StreamError("Connection failed")
    
    except requests.exceptions.HTTPError as e:
        raise StreamError(f"HTTP error: {e}")

class StreamError(Exception):
    pass

# Usage with retry
def stream_with_retry(messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            result = ""
            for chunk in safe_stream_chat(messages):
                result += chunk
                print(chunk, end="", flush=True)
            return result
        except StreamError as e:
            if attempt < max_retries - 1:
                print(f"\nRetrying ({attempt + 1}/{max_retries})...")
                time.sleep(2 ** attempt)
            else:
                raise
```

### Graceful Degradation

```python
def chat_with_fallback(messages):
    """Try streaming, fall back to regular request."""
    try:
        # Try streaming first
        result = ""
        for chunk in safe_stream_chat(messages):
            result += chunk
            print(chunk, end="", flush=True)
        return result
    
    except StreamError:
        # Fall back to non-streaming
        print("\nStreaming failed, using regular request...")
        response = requests.post(
            "http://localhost:8000/api/sendMessage",
            json={"messages": messages}
        )
        return response.json()["content"]
```

---

## Best Practices

### 1. Buffer Incomplete Lines

NDJSON may arrive in chunks that don't align with line boundaries:

```python
buffer = ""

for chunk in response.iter_content():
    buffer += chunk.decode('utf-8')
    
    while '\n' in buffer:
        line, buffer = buffer.split('\n', 1)
        if line.strip():
            event = json.loads(line)
            process_event(event)
```

### 2. Handle Partial Updates

Don't assume events arrive in a specific order:

```javascript
let state = {
    text: '',
    toolCalls: [],
    executedTools: [],
    commands: [],
    executedCommands: [],
    done: false,
    error: null
};

function processEvent(event) {
    switch (event.type) {
        case 'text_delta':
            state.text += event.text;
            break;
        case 'tool_calls':
            state.toolCalls.push(...event.tool_calls);
            break;
        case 'executed_tool_calls':
            state.executedTools.push(...event.executed_tool_calls);
            break;
        case 'commands':
            state.commands.push(...event.commands);
            break;
        case 'executed_commands':
            state.executedCommands.push(...event.executed_cmds);
            break;
        case 'done':
            state.done = true;
            break;
        case 'error':
            state.error = event.error;
            break;
    }
    
    updateUI(state);
}
```

### 3. Implement Timeouts

```python
import time

def stream_with_timeout(messages, timeout=60):
    """Stream with overall timeout."""
    start_time = time.time()
    
    for chunk in safe_stream_chat(messages):
        if time.time() - start_time > timeout:
            raise TimeoutError("Stream timeout exceeded")
        yield chunk
```

### 4. Show Progress Indicators

```jsx
function StreamingResponse({ text, isStreaming }) {
    return (
        <div className="response">
            {text}
            {isStreaming && (
                <span className="streaming-indicator">
                    <span className="cursor">▌</span>
                    <span className="status">Generating...</span>
                </span>
            )}
        </div>
    );
}
```

### 5. Enable Cancellation

```javascript
const controller = new AbortController();

// Start streaming
fetch('/api/sendMessageStream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal: controller.signal
});

// Cancel if needed
document.getElementById('cancel').onclick = () => {
    controller.abort();
};
```

### 6. Batch UI Updates

```javascript
let pendingText = '';
let updateScheduled = false;

function processTextDelta(text) {
    pendingText += text;
    
    if (!updateScheduled) {
        updateScheduled = true;
        requestAnimationFrame(() => {
            document.getElementById('response').textContent += pendingText;
            pendingText = '';
            updateScheduled = false;
        });
    }
}
```

---

## See Also

- [Agent Server API Reference](../api-reference/agent-server.md)
- [Schemas API Reference](../api-reference/schemas.md)
- [Message Protocol Guide](./message-protocol.md)

