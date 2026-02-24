# Default Agno Toolkit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a feature-flagged default toolkit that bundles 5 Agno built-in toolkits (File, LocalFileSystem, Python, Shell, FileGeneration) into DCAF agents when `DCAF_DEFAULT_TOOLKIT=true`.

**Architecture:** New `_build_default_toolkits()` method in `AgnoAdapter` returns toolkit instances. In `_create_agent_async()`, check the env var and merge default toolkits with user tools before passing to `AgnoAgent`. Config constant added to `EnvVars`.

**Tech Stack:** Python 3.11+, agno SDK (agno.tools.*), pytest, monkeypatch for env vars

---

### Task 1: Create branch

**Step 1: Create and switch to the `toolkit` branch tracking main**

```bash
git checkout -b toolkit main
```

**Step 2: Verify branch**

```bash
git branch --show-current
```

Expected: `toolkit`

---

### Task 2: Add `DEFAULT_TOOLKIT` env var to config

**Files:**
- Modify: `dcaf/core/config.py:98-101`
- Test: `tests/core/test_config.py`

**Step 1: Write the failing test**

Add to `tests/core/test_config.py`:

```python
class TestEnvVarsConstants:
    def test_default_toolkit_env_var_defined(self):
        from dcaf.core.config import EnvVars

        assert hasattr(EnvVars, "DEFAULT_TOOLKIT")
        assert EnvVars.DEFAULT_TOOLKIT == "DCAF_DEFAULT_TOOLKIT"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_config.py::TestEnvVarsConstants::test_default_toolkit_env_var_defined -v`
Expected: FAIL with `AttributeError: type object 'EnvVars' has no attribute 'DEFAULT_TOOLKIT'`

**Step 3: Write minimal implementation**

In `dcaf/core/config.py`, add to the `EnvVars` class after line 101 (`DISABLE_TOOL_FILTERING`), inside the "Behavior flags" section:

```python
    DEFAULT_TOOLKIT = "DCAF_DEFAULT_TOOLKIT"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_config.py::TestEnvVarsConstants -v`
Expected: PASS

**Step 5: Commit**

```bash
git add dcaf/core/config.py tests/core/test_config.py
git commit -m "feat(config): add DCAF_DEFAULT_TOOLKIT env var constant"
```

---

### Task 3: Add `_build_default_toolkits()` method to AgnoAdapter

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py`
- Test: `tests/core/test_agno_adapter.py`

**Step 1: Write the failing test**

Add to `tests/core/test_agno_adapter.py`:

```python
class TestDefaultToolkit:
    """Tests for the default toolkit feature flag."""

    def test_build_default_toolkits_returns_five_toolkits(self):
        """Verify _build_default_toolkits returns all 5 Agno toolkit instances."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        toolkits = adapter._build_default_toolkits()

        assert len(toolkits) == 5, f"Expected 5 toolkits, got {len(toolkits)}"

    def test_build_default_toolkits_returns_correct_types(self):
        """Verify each toolkit is the correct Agno type."""
        from agno.tools.file import FileTools
        from agno.tools.file_generation import FileGenerationTools
        from agno.tools.local_file_system import LocalFileSystemTools
        from agno.tools.python import PythonTools
        from agno.tools.shell import ShellTools

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        toolkits = adapter._build_default_toolkits()

        toolkit_types = {type(t) for t in toolkits}
        expected_types = {FileTools, LocalFileSystemTools, PythonTools, ShellTools, FileGenerationTools}

        assert toolkit_types == expected_types, (
            f"Expected types {expected_types}, got {toolkit_types}"
        )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_agno_adapter.py::TestDefaultToolkit -v`
Expected: FAIL with `AttributeError: 'AgnoAdapter' object has no attribute '_build_default_toolkits'`

**Step 3: Write minimal implementation**

Add imports near the top of `dcaf/core/adapters/outbound/agno/adapter.py` (after the existing agno imports around line 25):

```python
from agno.tools.file import FileTools
from agno.tools.file_generation import FileGenerationTools
from agno.tools.local_file_system import LocalFileSystemTools
from agno.tools.python import PythonTools
from agno.tools.shell import ShellTools
```

Add method to the `AgnoAdapter` class (after `_resolve_skills` method, around line 697):

```python
    def _build_default_toolkits(self) -> list[Any]:
        """
        Build the default set of Agno toolkits.

        Returns a list of Agno toolkit instances: FileTools, LocalFileSystemTools,
        PythonTools, ShellTools, and FileGenerationTools.

        These are native Agno toolkits and are passed directly to AgnoAgent
        without conversion through _convert_tools_to_agno().
        """
        return [
            FileTools(),
            LocalFileSystemTools(),
            PythonTools(),
            ShellTools(),
            FileGenerationTools(),
        ]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_agno_adapter.py::TestDefaultToolkit -v`
Expected: PASS

**Step 5: Commit**

```bash
git add dcaf/core/adapters/outbound/agno/adapter.py tests/core/test_agno_adapter.py
git commit -m "feat(adapter): add _build_default_toolkits method"
```

---

### Task 4: Wire feature flag into `_create_agent_async()`

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py:640-667`
- Test: `tests/core/test_agno_adapter.py`

**Step 1: Write the failing tests**

Add to the `TestDefaultToolkit` class in `tests/core/test_agno_adapter.py`:

```python
    def test_default_toolkit_disabled_by_default(self, monkeypatch):
        """Verify default toolkit is NOT included when env var is unset."""
        monkeypatch.delenv("DCAF_DEFAULT_TOOLKIT", raising=False)

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")

        from dcaf.core import tool

        @tool(description="User tool")
        def my_tool(x: str) -> str:
            return x

        agno_tools = adapter._prepare_tools_with_defaults([my_tool], platform_context=None)
        # Should only have the user tool (converted), no default toolkits
        assert len(agno_tools) == 1

    def test_default_toolkit_enabled_merges_with_user_tools(self, monkeypatch):
        """Verify default toolkits are merged when env var is true."""
        monkeypatch.setenv("DCAF_DEFAULT_TOOLKIT", "true")

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")

        from dcaf.core import tool

        @tool(description="User tool")
        def my_tool(x: str) -> str:
            return x

        agno_tools = adapter._prepare_tools_with_defaults([my_tool], platform_context=None)
        # Should have 5 default toolkits + 1 user tool = 6
        assert len(agno_tools) == 6

    def test_default_toolkit_enabled_no_user_tools(self, monkeypatch):
        """Verify default toolkits work even with no user tools."""
        monkeypatch.setenv("DCAF_DEFAULT_TOOLKIT", "true")

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")

        agno_tools = adapter._prepare_tools_with_defaults([], platform_context=None)
        # Should have 5 default toolkits
        assert len(agno_tools) == 5
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_agno_adapter.py::TestDefaultToolkit::test_default_toolkit_disabled_by_default -v`
Expected: FAIL with `AttributeError: 'AgnoAdapter' object has no attribute '_prepare_tools_with_defaults'`

**Step 3: Write minimal implementation**

Add a new method `_prepare_tools_with_defaults` to `AgnoAdapter` and update `_create_agent_async` to use it.

Add method (after `_build_default_toolkits`):

```python
    def _prepare_tools_with_defaults(
        self,
        tools: list[Any],
        platform_context: dict[str, Any] | None = None,
    ) -> list[Any]:
        """
        Convert user tools and optionally prepend default toolkits.

        When DCAF_DEFAULT_TOOLKIT=true, the 5 built-in Agno toolkits are
        prepended to the tools list. Default toolkits are native Agno objects
        and bypass _convert_tools_to_agno().

        Args:
            tools: List of dcaf Tool objects from the caller.
            platform_context: Optional platform context for tool injection.

        Returns:
            Combined list of Agno-compatible tools.
        """
        agno_tools = self._convert_tools_to_agno(tools, platform_context)

        if os.getenv("DCAF_DEFAULT_TOOLKIT", "false").lower() == "true":
            default_toolkits = self._build_default_toolkits()
            agno_tools = default_toolkits + agno_tools
            logger.info(f"Default toolkit enabled: added {len(default_toolkits)} built-in toolkits")

        return agno_tools
```

Update `_create_agent_async` — replace line 644:

```python
        agno_tools = self._convert_tools_to_agno(tools, platform_context)
```

with:

```python
        agno_tools = self._prepare_tools_with_defaults(tools, platform_context)
```

**Step 4: Run all tests to verify they pass**

Run: `pytest tests/core/test_agno_adapter.py::TestDefaultToolkit -v`
Expected: All 5 tests PASS

**Step 5: Run full test suite**

Run: `pytest tests/core/test_agno_adapter.py -v`
Expected: All tests PASS (existing tests unaffected)

**Step 6: Commit**

```bash
git add dcaf/core/adapters/outbound/agno/adapter.py tests/core/test_agno_adapter.py
git commit -m "feat(adapter): wire DCAF_DEFAULT_TOOLKIT feature flag into agent creation"
```

---

### Task 5: Run full quality checks

**Step 1: Run pytest**

Run: `pytest -v`
Expected: All tests PASS

**Step 2: Run ruff lint**

Run: `ruff check dcaf/core/config.py dcaf/core/adapters/outbound/agno/adapter.py`
Expected: No errors

**Step 3: Run ruff format**

Run: `ruff format dcaf/core/config.py dcaf/core/adapters/outbound/agno/adapter.py`
Expected: Files already formatted or formatted

**Step 4: Run mypy**

Run: `mypy dcaf/core/config.py dcaf/core/adapters/outbound/agno/adapter.py`
Expected: No errors

**Step 5: Run import linter**

Run: `lint-imports`
Expected: No violations

**Step 6: Commit any formatting fixes if needed**

```bash
git add -u && git commit -m "chore: fix lint/format issues"
```

(Skip if no changes.)
