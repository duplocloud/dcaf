# Additional Agno Toolkits Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to inject additional Agno toolkits into DCAF agents via the `DCAF_ADDITIONAL_TOOLS` environment variable.

**Architecture:** New `_load_additional_toolkits()` method in `AgnoAdapter` dynamically imports and instantiates Agno toolkit classes from a comma-separated env var. Integrated into existing `_prepare_tools_with_defaults()` pipeline.

**Tech Stack:** Python importlib, Agno SDK toolkits, pytest with monkeypatch

---

### Task 1: Add `ADDITIONAL_TOOLS` constant to EnvVars

**Files:**
- Modify: `dcaf/core/config.py:102`
- Test: `tests/core/test_config.py:196-201`

**Step 1: Write the failing test**

Add a new test method to `TestEnvVarsConstants` in `tests/core/test_config.py` (after line 201):

```python
    def test_additional_tools_env_var_defined(self):
        from dcaf.core.config import EnvVars

        assert hasattr(EnvVars, "ADDITIONAL_TOOLS")
        assert EnvVars.ADDITIONAL_TOOLS == "DCAF_ADDITIONAL_TOOLS"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_config.py::TestEnvVarsConstants::test_additional_tools_env_var_defined -v`
Expected: FAIL with `AssertionError` (attribute does not exist)

**Step 3: Write minimal implementation**

In `dcaf/core/config.py`, add after line 102 (`DEFAULT_TOOLKIT`):

```python
    ADDITIONAL_TOOLS = "DCAF_ADDITIONAL_TOOLS"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_config.py::TestEnvVarsConstants -v`
Expected: PASS (both tests)

**Step 5: Commit**

```bash
git add dcaf/core/config.py tests/core/test_config.py
git commit -m "feat(config): add ADDITIONAL_TOOLS env var constant"
```

---

### Task 2: Add `_load_additional_toolkits()` method — empty env var returns empty list

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py:720` (after `_build_default_toolkits`)
- Test: `tests/core/test_agno_adapter.py:672` (after `TestDefaultToolkit`)

**Step 1: Write the failing test**

Add a new test class `TestAdditionalToolkits` after `TestDefaultToolkit` in `tests/core/test_agno_adapter.py` (after line 672):

```python
class TestAdditionalToolkits:
    """Tests for the DCAF_ADDITIONAL_TOOLS feature."""

    def test_load_additional_toolkits_returns_empty_when_unset(self, monkeypatch):
        """Verify empty list when DCAF_ADDITIONAL_TOOLS is not set."""
        from dcaf.core.config import EnvVars

        monkeypatch.delenv(EnvVars.ADDITIONAL_TOOLS, raising=False)

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        toolkits = adapter._load_additional_toolkits()

        assert toolkits == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_agno_adapter.py::TestAdditionalToolkits::test_load_additional_toolkits_returns_empty_when_unset -v`
Expected: FAIL with `AttributeError: 'AgnoAdapter' object has no attribute '_load_additional_toolkits'`

**Step 3: Write minimal implementation**

In `dcaf/core/adapters/outbound/agno/adapter.py`, add `import importlib` to the imports (after line 19, alongside existing `import os`). Then add a new method after `_build_default_toolkits()` (after line 720):

```python
    def _load_additional_toolkits(self) -> list[Any]:
        """
        Load additional Agno toolkits from the DCAF_ADDITIONAL_TOOLS env var.

        The env var is a comma-separated list of entries in the format
        ``<submodule>.<ClassName>``, resolved as
        ``from agno.tools.<submodule> import <ClassName>``.

        Example:
            DCAF_ADDITIONAL_TOOLS="neo4j.Neo4jTools,duckdb.DuckDbTools"

        Invalid entries are logged as warnings and skipped.

        Returns:
            List of instantiated Agno toolkit objects.
        """
        raw = os.getenv(EnvVars.ADDITIONAL_TOOLS, "")
        if not raw.strip():
            return []

        toolkits: list[Any] = []
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue

            # Split on last dot: submodule.ClassName
            dot_index = entry.rfind(".")
            if dot_index <= 0:
                logger.warning(f"Invalid DCAF_ADDITIONAL_TOOLS entry '{entry}': expected format 'submodule.ClassName'")
                continue

            submodule = entry[:dot_index]
            class_name = entry[dot_index + 1:]
            module_path = f"agno.tools.{submodule}"

            try:
                module = importlib.import_module(module_path)
            except ImportError:
                logger.warning(f"Failed to import module '{module_path}' for DCAF_ADDITIONAL_TOOLS entry '{entry}'")
                continue

            cls = getattr(module, class_name, None)
            if cls is None:
                logger.warning(f"Class '{class_name}' not found in module '{module_path}'")
                continue

            try:
                toolkits.append(cls())
                logger.info(f"Loaded additional toolkit: {class_name} from {module_path}")
            except Exception as e:
                logger.warning(f"Failed to instantiate '{class_name}' from '{module_path}': {e}")

        return toolkits
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_agno_adapter.py::TestAdditionalToolkits::test_load_additional_toolkits_returns_empty_when_unset -v`
Expected: PASS

**Step 5: Commit**

```bash
git add dcaf/core/adapters/outbound/agno/adapter.py tests/core/test_agno_adapter.py
git commit -m "feat(adapter): add _load_additional_toolkits method"
```

---

### Task 3: Test loading valid toolkit entries

**Files:**
- Test: `tests/core/test_agno_adapter.py` (add to `TestAdditionalToolkits`)

**Step 1: Write the test**

Add to `TestAdditionalToolkits`:

```python
    def test_load_additional_toolkits_returns_valid_toolkits(self, monkeypatch):
        """Verify valid entries are imported and instantiated."""
        from dcaf.core.config import EnvVars

        # Use toolkits already available in agno (no extra install needed)
        monkeypatch.setenv(EnvVars.ADDITIONAL_TOOLS, "file.FileTools,shell.ShellTools")

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        toolkits = adapter._load_additional_toolkits()

        assert len(toolkits) == 2

        from agno.tools.file import FileTools
        from agno.tools.shell import ShellTools

        toolkit_types = {type(t) for t in toolkits}
        assert toolkit_types == {FileTools, ShellTools}
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/core/test_agno_adapter.py::TestAdditionalToolkits::test_load_additional_toolkits_returns_valid_toolkits -v`
Expected: PASS (implementation from Task 2 handles this)

**Step 3: Commit**

```bash
git add tests/core/test_agno_adapter.py
git commit -m "test(adapter): add test for loading valid additional toolkits"
```

---

### Task 4: Test that invalid entries are skipped gracefully

**Files:**
- Test: `tests/core/test_agno_adapter.py` (add to `TestAdditionalToolkits`)

**Step 1: Write the tests**

Add to `TestAdditionalToolkits`:

```python
    def test_load_additional_toolkits_skips_invalid_format(self, monkeypatch):
        """Verify entries without a dot are skipped."""
        from dcaf.core.config import EnvVars

        monkeypatch.setenv(EnvVars.ADDITIONAL_TOOLS, "NoDotsHere")

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        toolkits = adapter._load_additional_toolkits()

        assert toolkits == []

    def test_load_additional_toolkits_skips_import_failure(self, monkeypatch):
        """Verify missing modules are skipped."""
        from dcaf.core.config import EnvVars

        monkeypatch.setenv(EnvVars.ADDITIONAL_TOOLS, "nonexistent_module.FakeTool")

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        toolkits = adapter._load_additional_toolkits()

        assert toolkits == []

    def test_load_additional_toolkits_skips_missing_class(self, monkeypatch):
        """Verify missing class in valid module is skipped."""
        from dcaf.core.config import EnvVars

        monkeypatch.setenv(EnvVars.ADDITIONAL_TOOLS, "file.NonExistentClass")

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        toolkits = adapter._load_additional_toolkits()

        assert toolkits == []

    def test_load_additional_toolkits_partial_success(self, monkeypatch):
        """Verify valid entries load even when mixed with invalid ones."""
        from dcaf.core.config import EnvVars

        monkeypatch.setenv(
            EnvVars.ADDITIONAL_TOOLS,
            "file.FileTools,nonexistent.Fake,shell.ShellTools",
        )

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")
        toolkits = adapter._load_additional_toolkits()

        assert len(toolkits) == 2
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/core/test_agno_adapter.py::TestAdditionalToolkits -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/core/test_agno_adapter.py
git commit -m "test(adapter): add error handling tests for additional toolkits"
```

---

### Task 5: Integrate `_load_additional_toolkits()` into `_prepare_tools_with_defaults()`

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py:741-748` (`_prepare_tools_with_defaults`)
- Test: `tests/core/test_agno_adapter.py` (add to `TestAdditionalToolkits`)

**Step 1: Write the failing test**

Add to `TestAdditionalToolkits`:

```python
    def test_prepare_tools_includes_additional_toolkits(self, monkeypatch):
        """Verify additional toolkits are appended in _prepare_tools_with_defaults."""
        from dcaf.core.config import EnvVars

        monkeypatch.delenv(EnvVars.DEFAULT_TOOLKIT, raising=False)
        monkeypatch.setenv(EnvVars.ADDITIONAL_TOOLS, "file.FileTools")

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")

        from dcaf.core import tool

        @tool(description="User tool")
        def my_tool(x: str) -> str:
            return x

        agno_tools = adapter._prepare_tools_with_defaults([my_tool], platform_context=None)
        # 1 user tool + 1 additional toolkit = 2
        assert len(agno_tools) == 2

    def test_prepare_tools_with_defaults_and_additional(self, monkeypatch):
        """Verify all three sources merge: defaults + user tools + additional."""
        from dcaf.core.config import EnvVars

        monkeypatch.setenv(EnvVars.DEFAULT_TOOLKIT, "true")
        monkeypatch.setenv(EnvVars.ADDITIONAL_TOOLS, "file.FileTools")

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test", provider="bedrock")

        from dcaf.core import tool

        @tool(description="User tool")
        def my_tool(x: str) -> str:
            return x

        agno_tools = adapter._prepare_tools_with_defaults([my_tool], platform_context=None)
        # 5 default toolkits + 1 user tool + 1 additional toolkit = 7
        assert len(agno_tools) == 7
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_agno_adapter.py::TestAdditionalToolkits::test_prepare_tools_includes_additional_toolkits -v`
Expected: FAIL — `len(agno_tools) == 1` (additional toolkits not yet wired in)

**Step 3: Write minimal implementation**

In `dcaf/core/adapters/outbound/agno/adapter.py`, modify `_prepare_tools_with_defaults()`. Replace lines 741-748:

```python
        agno_tools = self._convert_tools_to_agno(tools, platform_context)

        if os.getenv(EnvVars.DEFAULT_TOOLKIT, "false").lower() == "true":
            default_toolkits = self._build_default_toolkits()
            agno_tools = default_toolkits + agno_tools
            logger.info(f"Default toolkit enabled: added {len(default_toolkits)} built-in toolkits")

        additional_toolkits = self._load_additional_toolkits()
        if additional_toolkits:
            agno_tools = agno_tools + additional_toolkits
            logger.info(
                f"Additional toolkits loaded: added {len(additional_toolkits)} toolkits"
            )

        return agno_tools
```

Also update the docstring for `_prepare_tools_with_defaults` to mention additional toolkits:

```python
    def _prepare_tools_with_defaults(
        self,
        tools: list[Any],
        platform_context: dict[str, Any] | None = None,
    ) -> list[Any]:
        """
        Convert user tools and optionally include default and additional toolkits.

        When DCAF_DEFAULT_TOOLKIT=true, the 5 built-in Agno toolkits are
        prepended to the tools list. When DCAF_ADDITIONAL_TOOLS is set,
        those toolkits are appended. Default and additional toolkits are
        native Agno objects and bypass _convert_tools_to_agno().

        Args:
            tools: List of dcaf Tool objects from the caller.
            platform_context: Optional platform context for tool injection.

        Returns:
            Combined list of Agno-compatible tools.
        """
```

**Step 4: Run all tests to verify they pass**

Run: `pytest tests/core/test_agno_adapter.py::TestAdditionalToolkits tests/core/test_agno_adapter.py::TestDefaultToolkit -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add dcaf/core/adapters/outbound/agno/adapter.py tests/core/test_agno_adapter.py
git commit -m "feat(adapter): integrate additional toolkits into tool preparation pipeline"
```

---

### Task 6: Run full test suite and quality checks

**Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS (except known `test_channel_routing.py` failures)

**Step 2: Run linter and formatter**

Run: `ruff check . && ruff format --check .`
Expected: No issues

**Step 3: Run type checker**

Run: `mypy dcaf/`
Expected: No new errors

**Step 4: Run import linter**

Run: `lint-imports`
Expected: No violations

**Step 5: Commit any formatting fixes if needed**

```bash
ruff format .
ruff check --fix .
git add -u
git commit -m "chore: fix formatting"
```
