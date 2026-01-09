# A2A Integration Fix Summary

## Issue

The A2A (Agent-to-Agent) integration was not working properly. Users reported that they couldn't connect to remote agents using the `RemoteAgent` client.

## Root Cause

The issue was caused by two problems in the `httpx` HTTP client configuration:

1. **httpx trusting environment variables**: By default, `httpx.Client()` has `trust_env=True`, which makes it respect environment proxy settings and other configurations. This was causing httpx to send malformed requests where the entire URL (including scheme and host) was being URL-encoded and sent as the path.

2. **localhost resolution issues**: When using `localhost`, httpx was encoding the full URL in the request path (`http%3A//localhost%3A8001/.well-known/agent.json` instead of `/.well-known/agent.json`), causing 404 errors.

### Example of the Problem

**Expected behavior:**
```
GET /.well-known/agent.json HTTP/1.1
Host: localhost:8001
```

**Actual behavior (before fix):**
```
GET http%3A//localhost%3A8001/.well-known/agent.json HTTP/1.1
```

This caused FastAPI to return 404 Not Found because the route was registered as `/.well-known/agent.json`, not the URL-encoded full URL.

## Solution

Fixed the `AgnoA2AClient` class in `/Users/chuckconway/Projects/dcaf/dcaf/core/a2a/adapters/agno.py`:

### 1. Added `trust_env=False` to httpx Client

```python
# Before
self._http_client = httpx.Client(timeout=60.0)

# After
self._http_client = httpx.Client(timeout=60.0, trust_env=False)
```

This prevents httpx from trusting environment variables that might interfere with URL resolution.

### 2. Added URL normalization for localhost

Replaced `localhost` with `127.0.0.1` in all methods to avoid any potential IPv6/proxy issues:

```python
# Example from fetch_agent_card method
normalized_url = url.replace("localhost", "127.0.0.1")
agent_card_url = f"{normalized_url}/.well-known/agent.json"
```

Then restored the original URL in the agent card for user-facing display.

## Changes Made

Modified file: `dcaf/core/a2a/adapters/agno.py`

1. `__init__`: Added `trust_env=False` to httpx.Client initialization
2. `fetch_agent_card`: Added URL normalization (localhost → 127.0.0.1)
3. `send_task`: Added URL normalization
4. `send_task_async`: Added URL normalization
5. `get_task_status`: Added URL normalization

## Verification

Created and ran `verify_a2a.py` which tests all major A2A features:

✅ Agent card discovery  
✅ Task execution  
✅ RemoteAgent client  
✅ Tool conversion for orchestration  

All tests pass successfully.

## Example Usage

```python
from dcaf.core import Agent, serve
from dcaf.core.a2a import RemoteAgent
from dcaf.tools import tool

# Start an A2A-enabled agent
@tool(description="List pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

agent = Agent(
    name="k8s-assistant",
    description="Kubernetes helper",
    tools=[list_pods],
)
serve(agent, port=8001, a2a=True)

# Connect to it from another process
k8s = RemoteAgent(url="http://localhost:8001")
result = k8s.send("List all pods")
print(result.text)
```

## Testing

To test the A2A integration:

```bash
# Terminal 1: Start an agent
python examples/a2a_example.py k8s

# Terminal 2: Run the verification
python verify_a2a.py
```

## Dependencies

The fix requires:
- `httpx` (already in requirements.txt)
- `aioboto3` (already in requirements.txt, needed for Bedrock runtime)

Make sure to install with:
```bash
uv pip install -r requirements.txt
```

## Impact

- **No breaking changes**: The API remains the same
- **Better reliability**: httpx client is more robust against environment configuration issues
- **Full functionality restored**: All A2A features now work as documented

## Related Files

- `/dcaf/core/a2a/adapters/agno.py` - Fixed httpx configuration
- `/examples/a2a_example.py` - Working example demonstrating A2A
- `/docs/core/a2a.md` - Complete A2A documentation
- `/verify_a2a.py` - Verification script (can be used for testing)
