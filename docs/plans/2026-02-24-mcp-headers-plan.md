# MCPTool Headers Support — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `headers` parameter to `MCPTool` so users can pass HTTP headers (e.g., Authorization) to authenticated MCP servers.

**Architecture:** Wrap a static `headers: dict[str, str]` as a `lambda: headers` and pass it to Agno's existing `header_provider` parameter. Validate at construction time that headers are only used with HTTP transports.

**Tech Stack:** Python, pytest, Agno MCPTools

---

### Task 1: Write failing tests for headers parameter

**Files:**
- Modify: `tests/core/test_mcp_tools.py`

**Step 1: Write the failing tests**

Add a new test class `TestMCPToolHeaders` after `TestMCPToolInitialization` (after line 98):

```python
class TestMCPToolHeaders:
    """Test headers parameter support."""

    def test_headers_stored_on_init(self):
        """Should store headers dict when provided."""
        from dcaf.mcp import MCPTool

        headers = {"Authorization": "Bearer token123"}
        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            headers=headers,
        )
        assert mcp._headers == headers

    def test_headers_none_by_default(self):
        """Headers should default to None when not provided."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(url="http://localhost:8000/mcp", transport="streamable-http")
        assert mcp._headers is None

    def test_headers_raises_for_stdio_transport(self):
        """Should raise ValueError if headers used with stdio transport."""
        from dcaf.mcp import MCPTool

        with pytest.raises(ValueError, match="headers.*only supported.*sse.*streamable-http"):
            MCPTool(
                command="python server.py",
                transport="stdio",
                headers={"Authorization": "Bearer token"},
            )

    def test_headers_allowed_with_sse_transport(self):
        """Should accept headers with sse transport."""
        from dcaf.mcp import MCPTool

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="sse",
            headers={"Authorization": "Bearer token"},
        )
        assert mcp._headers == {"Authorization": "Bearer token"}

    def test_headers_forwarded_as_header_provider(self):
        """Should forward headers as header_provider callable to Agno MCPTools."""
        pytest.importorskip("mcp", reason="MCP package not installed")
        from dcaf.mcp import MCPTool

        headers = {"Authorization": "Bearer token123"}
        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
            headers=headers,
        )

        with patch("agno.tools.mcp.MCPTools") as MockAgnoMCPTools:
            mock_instance = Mock()
            mock_instance.functions = {}
            MockAgnoMCPTools.return_value = mock_instance

            mcp._create_agno_mcp_tools()

            # Verify header_provider was passed
            call_kwargs = MockAgnoMCPTools.call_args[1]
            assert "header_provider" in call_kwargs
            assert callable(call_kwargs["header_provider"])
            assert call_kwargs["header_provider"]() == headers

    def test_no_header_provider_when_headers_none(self):
        """Should not pass header_provider when headers is None."""
        pytest.importorskip("mcp", reason="MCP package not installed")
        from dcaf.mcp import MCPTool

        mcp = MCPTool(
            url="http://localhost:8000/mcp",
            transport="streamable-http",
        )

        with patch("agno.tools.mcp.MCPTools") as MockAgnoMCPTools:
            mock_instance = Mock()
            mock_instance.functions = {}
            MockAgnoMCPTools.return_value = mock_instance

            mcp._create_agno_mcp_tools()

            call_kwargs = MockAgnoMCPTools.call_args[1]
            assert call_kwargs.get("header_provider") is None
```

**Step 2: Run the tests to verify they fail**

Run: `pytest tests/core/test_mcp_tools.py::TestMCPToolHeaders -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'headers'`

**Step 3: Commit the failing tests**

```bash
git add tests/core/test_mcp_tools.py
git commit -m "test: add failing tests for MCPTool headers parameter"
```

---

### Task 2: Implement headers support in MCPTool

**Files:**
- Modify: `dcaf/mcp/tools.py:146-285`

**Step 1: Add headers parameter to `__init__`**

In `dcaf/mcp/tools.py`, add the `headers` parameter to `__init__` (after `post_hook` on line 160):

```python
    def __init__(
        self,
        command: str | None = None,
        *,
        url: str | None = None,
        env: dict[str, str] | None = None,
        transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
        timeout_seconds: int = 10,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
        tool_name_prefix: str | None = None,
        refresh_connection: bool = False,
        auto_approve_tools: list[str] | None = None,
        pre_hook: PreHookFunc | None = None,
        post_hook: PostHookFunc | None = None,
        headers: dict[str, str] | None = None,
    ):
```

Add validation after the existing transport checks (after line 202):

```python
        if headers is not None and transport == "stdio":
            raise ValueError(
                "headers are only supported with sse or streamable-http transport"
            )
```

Store the value (after `self._post_hook = post_hook` on line 216):

```python
        self._headers = headers
```

**Step 2: Forward headers in `_create_agno_mcp_tools()`**

In the `_create_agno_mcp_tools` method, add header_provider construction before the `AgnoMCPTools(...)` call (before line 275):

```python
        header_provider = None
        if self._headers:
            _headers = self._headers
            header_provider = lambda: _headers
```

Then add `header_provider=header_provider` to the `AgnoMCPTools(...)` constructor call:

```python
        self._agno_mcp_tools = AgnoMCPTools(
            command=self._command,
            url=self._url,
            env=self._env,
            transport=self._transport,
            timeout_seconds=self._timeout_seconds,
            include_tools=self._include_tools,
            exclude_tools=agno_exclude or None,
            tool_name_prefix=self._tool_name_prefix,
            refresh_connection=self._refresh_connection,
            header_provider=header_provider,
        )
```

**Step 3: Update the docstring**

Add to the Args section of `__init__` docstring (after the post_hook description):

```
            headers: Dictionary of HTTP headers to send with every request to the
                    MCP server. Only supported with sse or streamable-http transport.
                    Example: {"Authorization": "Bearer <token>"}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_mcp_tools.py -v`
Expected: ALL PASS

**Step 5: Run full quality checks**

Run: `ruff check dcaf/mcp/tools.py && ruff format --check dcaf/mcp/tools.py`
Expected: PASS

**Step 6: Commit**

```bash
git add dcaf/mcp/tools.py
git commit -m "feat(mcp): add headers parameter to MCPTool"
```

---

### Task 3: Update documentation

**Files:**
- Modify: `docs/guides/mcp-tools.md` (if it documents MCPTool constructor parameters)

**Step 1: Check docs and add headers example**

Read `docs/guides/mcp-tools.md` and add an example showing headers usage for authenticated MCP servers. Add a section like:

```markdown
### Authenticated MCP Servers

Pass HTTP headers (e.g., Authorization) to MCP servers that require authentication:

    mcp_tool = MCPTool(
        url="https://mcp-server.example.com/mcp",
        transport="streamable-http",
        headers={
            "Authorization": f"Bearer {os.environ['MCP_TOKEN']}"
        },
    )
```

**Step 2: Run docs build**

Run: `mkdocs build --strict`
Expected: PASS

**Step 3: Commit**

```bash
git add docs/guides/mcp-tools.md
git commit -m "docs(mcp): add headers usage example"
```

---

### Task 4: Final verification

**Step 1: Run full test suite**

Run: `pytest tests/core/test_mcp_tools.py -v`
Expected: ALL PASS

**Step 2: Run linting and formatting**

Run: `ruff check . && ruff format --check .`
Expected: PASS

**Step 3: Run type check**

Run: `mypy dcaf/mcp/tools.py`
Expected: PASS (or only pre-existing issues)
