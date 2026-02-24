# A2A Integration - Quick Start Guide

**Status:** ✅ Working  
**AWS Profile Used:** `test10`  
**Date Tested:** January 9, 2026

---

## 1-Minute Quick Start

```bash
# Set AWS credentials
export AWS_PROFILE=test10

# Run tests
cd /Users/chuckconway/Projects/dcaf
source .venv/bin/activate
python -m pytest tests/test_a2a_integration.py -v

# Expected: ✅ 7 passed
```

---

## What Just Got Fixed

**Problem:** A2A integration was failing with 404 errors  
**Root Cause:** httpx client was URL-encoding full URLs  
**Solution:** Set `trust_env=False` in httpx client + URL normalization  
**Files Changed:** `dcaf/core/a2a/adapters/agno.py`

---

## Live Example Output

```
======================================================================
  ✅ ALL TESTS PASSED - A2A INTEGRATION WORKING
======================================================================

Verified Capabilities:
  ✓ Agent discovery via HTTP
  ✓ Agent card fetch (/.well-known/agent.json)
  ✓ Task execution (/a2a/tasks/send)
  ✓ RemoteAgent client working
  ✓ Tool conversion for orchestration
  ✓ No 404 errors (httpx fix applied)
  ✓ Clean output suitable for handoff

======================================================================
  READY FOR PRODUCTION DEPLOYMENT
======================================================================
```

**Server Logs (Clean):**
```
INFO | A2A protocol enabled
INFO | Starting DCAF server at http://0.0.0.0:8001
INFO | A2A Endpoints:
INFO |   GET  http://0.0.0.0:8001/.well-known/agent.json
INFO |   POST http://0.0.0.0:8001/a2a/tasks/send
Starting Kubernetes agent on port 8001...
INFO: 127.0.0.1:51308 - "GET /.well-known/agent.json HTTP/1.1" 200 OK
INFO: 127.0.0.1:51308 - "POST /a2a/tasks/send HTTP/1.1" 200 OK
```

**No AWS credential errors when using proper profile!**

---

## Production Usage

### Simple Agent

```python
from dcaf.core import Agent, serve

agent = Agent(
    name="k8s-assistant",
    description="Kubernetes helper",
    tools=[list_pods, delete_pod],
    aws_profile="test10",  # ← Use your AWS profile
)

serve(agent, port=8001, a2a=True)
```

### Calling Remote Agent

```python
from dcaf.core.a2a import RemoteAgent

k8s = RemoteAgent(url="http://localhost:8001")
result = k8s.send("List failing pods")
print(result.text)
```

### Multi-Agent Orchestration

```python
from dcaf.core import Agent
from dcaf.core.a2a import RemoteAgent

k8s = RemoteAgent(url="http://k8s-agent:8001")
aws = RemoteAgent(url="http://aws-agent:8002")

orchestrator = Agent(
    tools=[k8s.as_tool(), aws.as_tool()],
    system="Route to appropriate specialist"
)
```

---

## Files for Handoff

### Documentation
- **This file**: Quick start overview
- `A2A_HANDOFF_EXAMPLE.md` - Complete engineer handoff guide
- `A2A_FIX_SUMMARY.md` - Technical fix details
- `A2A_INVESTIGATION_REPORT.md` - Full investigation
- `docs/core/a2a.md` - API reference & examples

### Code
- `dcaf/core/a2a/` - A2A implementation
- `examples/a2a_example.py` - Working example
- `tests/test_a2a_integration.py` - Test suite

### Logs
- Client logs: Console output
- Server logs: `/tmp/k8s_clean.log` (when redirected)

---

## Verification Checklist

- [x] Unit tests pass (7/7)
- [x] Integration test works
- [x] Server logs clean (200 OK, no 404s)
- [x] AWS profile configured correctly
- [x] Agent discovery working
- [x] Task execution working
- [x] Tool conversion working
- [x] Documentation complete
- [ ] Next engineer reviews
- [ ] Next engineer runs tests
- [ ] Ready for deployment

---

## Support

**Questions?** See:
- Complete docs: `A2A_HANDOFF_EXAMPLE.md`
- API docs: `docs/core/a2a.md`
- Working example: `examples/a2a_example.py`
