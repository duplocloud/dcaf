# tests/ — Test Conventions

## Running Tests

```bash
# All tests (default: verbose, short traceback)
pytest

# Single file
pytest tests/core/test_agent.py -v

# By pattern
pytest -k "test_approval" -v

# Quick mode
pytest --tb=short -q
```

## Structure

```
tests/
├── core/                    # Core API tests (~24 files)
│   ├── test_agent.py        # Main Agent facade tests
│   ├── test_agent_service.py
│   ├── test_approval_service.py
│   ├── test_interceptors.py
│   ├── test_core_domain.py  # Entity behavior, state machines
│   ├── test_agno_adapter.py # LLM adapter integration
│   ├── test_skills.py       # Skills feature
│   ├── test_a2a_integration.py
│   ├── test_mcp_tools.py
│   ├── test_config.py
│   ├── test_session.py
│   ├── test_websocket.py
│   └── mcp_test_server.py   # Test MCP server fixture
└── v1/                      # Legacy API tests
```

## Conventions

- **Async**: `asyncio_mode = "auto"` — just write `async def test_*()`, no decorator needed
- **Fakes over mocks**: Use `dcaf.core.testing.fakes` (FakeAgentRuntime, FakeRepository) instead of unittest.mock where possible
- **Builders**: Use `dcaf.core.testing.builders` for test object construction
- **Fixtures**: Shared fixtures in `dcaf.core.testing.fixtures`
- **Naming**: `test_<what>_<scenario>` (e.g., `test_agent_run_with_approval_required`)
- **Relaxed lint rules**: Tests allow `assert`, hardcoded passwords, and extra function args (see `pyproject.toml` per-file-ignores)
