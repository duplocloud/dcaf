# A2A Integration Investigation Report

**Date:** January 9, 2026  
**Issue:** A2A integration not working  
**Status:** ✅ FIXED

## Executive Summary

The A2A (Agent-to-Agent) integration in DCAF was not functioning due to an httpx client configuration issue. The problem has been identified and fixed. All A2A features are now working correctly.

## Problem Description

Users reported that the A2A integration wasn't working. When attempting to connect to remote agents using `RemoteAgent`, the connection would fail with 404 errors.

## Root Cause Analysis

### Primary Issue: httpx Client Configuration

The httpx HTTP client was configured with `trust_env=True` (the default), which caused it to respect environment variables and proxy settings. This led to malformed HTTP requests where:

1. The full URL (including scheme and host) was being URL-encoded and sent as the path
2. Instead of sending `GET /.well-known/agent.json`, it was sending `GET http%3A//localhost%3A8001/.well-known/agent.json`
3. FastAPI couldn't match this to the registered route, resulting in 404 errors

### Secondary Issue: localhost Resolution

When using `localhost` in URLs, httpx exhibited unusual behavior in some environments, further compounding the routing issues.

## Solution Implemented

### Changed Files

1. **`dcaf/core/a2a/adapters/agno.py`**
   - Added `trust_env=False` to httpx.Client initialization
   - Added URL normalization (localhost → 127.0.0.1) in all HTTP methods
   - Restored original URL in agent card for display purposes

### Code Changes

```python
# Before
self._http_client = httpx.Client(timeout=60.0)

# After  
self._http_client = httpx.Client(timeout=60.0, trust_env=False)
```

```python
# URL normalization in all methods
normalized_url = url.replace("localhost", "127.0.0.1")
agent_card_url = f"{normalized_url}/.well-known/agent.json"
```

## Verification

### Test Results

Created comprehensive test suite in `tests/test_a2a_integration.py`:

- ✅ `test_generate_agent_card` - Agent card generation
- ✅ `test_agent_card_endpoint` - Agent card HTTP endpoint
- ✅ `test_task_send_endpoint` - Task execution
- ✅ `test_task_with_approval_needed` - Approval workflow
- ✅ `test_remote_agent_as_tool` - Tool conversion
- ✅ `test_a2a_routes_are_registered` - Route registration
- ✅ `test_a2a_routes_not_registered_when_disabled` - Route opt-out

All 7 tests pass successfully.

### Integration Testing

Verified end-to-end workflow:

1. ✅ Start an A2A-enabled agent
2. ✅ Connect with RemoteAgent client
3. ✅ Fetch agent card
4. ✅ Send tasks and receive responses
5. ✅ Convert RemoteAgent to tool for orchestration

## Usage Examples

### Basic Usage

```python
from dcaf.core import Agent, serve
from dcaf.core.a2a import RemoteAgent

# Server side
agent = Agent(
    name="k8s-assistant",
    description="Kubernetes helper",
    tools=[list_pods, delete_pod],
)
serve(agent, port=8001, a2a=True)

# Client side
k8s = RemoteAgent(url="http://localhost:8001")
result = k8s.send("List pods")
print(result.text)
```

### Orchestration Pattern

```python
from dcaf.core import Agent
from dcaf.core.a2a import RemoteAgent

# Connect to specialist agents
k8s = RemoteAgent(url="http://k8s-agent:8001")
aws = RemoteAgent(url="http://aws-agent:8002")

# Create orchestrator
orchestrator = Agent(
    tools=[k8s.as_tool(), aws.as_tool()],
    system="Route requests to specialist agents"
)
```

## Testing Instructions

### Quick Test

```bash
# In the project directory
python examples/a2a_example.py k8s
# In another terminal
python examples/a2a_example.py client
```

### Run Test Suite

```bash
python -m pytest tests/test_a2a_integration.py -v
```

## Dependencies

Ensure these are installed:

```bash
uv pip install -r requirements.txt
```

Required packages:
- `httpx` - HTTP client for A2A communication
- `aioboto3` - Async AWS Bedrock support

## Documentation

- **API Documentation:** `docs/core/a2a.md`
- **Implementation Summary:** `A2A_IMPLEMENTATION_SUMMARY.md`
- **Fix Summary:** `A2A_FIX_SUMMARY.md`
- **Examples:** `examples/a2a_example.py`

## Impact Assessment

- **Breaking Changes:** None
- **API Changes:** None (internal fix only)
- **Performance:** No significant impact
- **Reliability:** Significantly improved

## Recommendations

1. ✅ Keep `trust_env=False` in httpx client configuration
2. ✅ Use URL normalization for localhost
3. ✅ Add integration tests to CI/CD pipeline
4. ✅ Document the httpx configuration requirement

## Additional Notes

### Why trust_env=False?

Setting `trust_env=False` prevents httpx from reading:
- HTTP_PROXY / HTTPS_PROXY environment variables
- NO_PROXY settings
- ~/.netrc files
- System trust store

This is appropriate for A2A communication which is typically:
- Local or internal network communication
- Not requiring system-wide proxy settings
- Direct agent-to-agent connections

### Localhost vs 127.0.0.1

While both should work identically, using 127.0.0.1 explicitly:
- Avoids IPv6 resolution issues
- Bypasses potential DNS lookups
- Provides more consistent behavior across environments

## Conclusion

The A2A integration is now fully functional. All features work as documented:

- ✅ Agent discovery via agent cards
- ✅ Task execution (sync and async)
- ✅ RemoteAgent client
- ✅ Tool conversion for orchestration
- ✅ Multi-agent patterns (peer-to-peer and orchestration)

The fix is minimal, focused, and has no breaking changes to the public API.
