"""
Tests for the Agno adapter, specifically the tool conversion logic.

These tests verify that:
1. The `parameters` argument is NOT passed to Agno's @tool decorator
2. Tools are converted correctly with name and description only
3. Platform context injection works via wrapper functions
4. Function signatures are preserved for Agno's inference

This addresses the bug: "Invalid tool configuration arguments: {'parameters'}"
"""

import inspect
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_tool():
    """Create a mock dcaf Tool object."""
    from dcaf.tools import tool

    @tool(description="Test tool that echoes input")
    def echo_tool(message: str, count: int = 1) -> str:
        return message * count

    return echo_tool


@pytest.fixture
def mock_tool_with_context():
    """Create a mock dcaf Tool that requires platform_context."""
    from dcaf.tools import tool

    @tool(description="Tool that uses platform context")
    def context_tool(query: str, platform_context: dict[str, Any] = None) -> str:
        tenant = platform_context.get("tenant_name", "unknown") if platform_context else "unknown"
        return f"Query '{query}' for tenant {tenant}"

    return context_tool


@pytest.fixture
def agno_adapter():
    """Create an AgnoAdapter instance for testing."""
    # We'll mock the Agno imports to avoid requiring Agno in tests
    with patch.dict(
        "sys.modules",
        {
            "agno": MagicMock(),
            "agno.agent": MagicMock(),
            "agno.models.aws": MagicMock(),
            "agno.models.message": MagicMock(),
            "agno.tools": MagicMock(),
            "agno.run.agent": MagicMock(),
        },
    ):
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(
            model_id="test-model",
            provider="bedrock",
        )
        return adapter


# =============================================================================
# Test: Parameters NOT passed to Agno decorator
# =============================================================================


class TestAgnoToolConversion:
    """Tests verifying the Agno tool conversion fix."""

    def test_agno_decorator_called_without_parameters_arg(self, mock_tool):
        """
        CRITICAL TEST: Verify that 'parameters' is NOT passed to agno_tool_decorator.

        This test catches the bug: "Invalid tool configuration arguments: {'parameters'}"

        The fix ensures we only pass 'name' and 'description' to the decorator,
        letting Agno infer the parameter schema from the function signature.
        """
        # Create a mock for the agno_tool_decorator
        mock_decorator = MagicMock()
        mock_decorator.return_value = lambda f: f  # Decorator returns the function

        with patch("dcaf.core.adapters.outbound.agno.adapter.agno_tool_decorator", mock_decorator):
            from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

            adapter = AgnoAdapter(model_id="test", provider="bedrock")

            # Convert the tool
            adapter._convert_tools_to_agno([mock_tool])

            # Verify decorator was called
            assert mock_decorator.called, "agno_tool_decorator should have been called"

            # Get the kwargs passed to the decorator
            call_kwargs = mock_decorator.call_args.kwargs

            # CRITICAL: 'parameters' should NOT be in the kwargs
            assert "parameters" not in call_kwargs, (
                f"'parameters' should NOT be passed to agno_tool_decorator! "
                f"Got kwargs: {call_kwargs}"
            )

            # Verify only 'name' and 'description' are passed
            assert "name" in call_kwargs, "Expected 'name' to be passed"
            assert "description" in call_kwargs, "Expected 'description' to be passed"
            assert call_kwargs["name"] == "echo_tool"
            assert call_kwargs["description"] == "Test tool that echoes input"

    def test_agno_decorator_only_valid_args(self, mock_tool):
        """
        Verify that only valid Agno decorator arguments are passed.

        Valid args per Agno docs: name, description, add_instructions, cache_dir,
        cache_results, cache_ttl, external_execution, instructions, post_hook,
        pre_hook, requires_confirmation, requires_user_input, show_result,
        stop_after_tool_call, strict, tool_hooks, user_input_fields
        """
        VALID_AGNO_KWARGS = {
            "add_instructions",
            "cache_dir",
            "cache_results",
            "cache_ttl",
            "description",
            "external_execution",
            "instructions",
            "name",
            "post_hook",
            "pre_hook",
            "requires_confirmation",
            "requires_user_input",
            "show_result",
            "stop_after_tool_call",
            "strict",
            "tool_hooks",
            "user_input_fields",
        }

        mock_decorator = MagicMock()
        mock_decorator.return_value = lambda f: f

        with patch("dcaf.core.adapters.outbound.agno.adapter.agno_tool_decorator", mock_decorator):
            from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

            adapter = AgnoAdapter(model_id="test", provider="bedrock")
            adapter._convert_tools_to_agno([mock_tool])

            call_kwargs = mock_decorator.call_args.kwargs

            # All kwargs should be in the valid set
            invalid_kwargs = set(call_kwargs.keys()) - VALID_AGNO_KWARGS
            assert not invalid_kwargs, (
                f"Invalid kwargs passed to agno_tool_decorator: {invalid_kwargs}"
            )


# =============================================================================
# Test: Platform Context Injection
# =============================================================================


class TestPlatformContextInjection:
    """Tests for platform_context injection into tools."""

    def test_wrapper_injects_platform_context(self, mock_tool_with_context):
        """Verify that platform_context is injected via wrapper function."""
        mock_decorator = MagicMock()
        captured_func = None

        def capture_decorated(f):
            nonlocal captured_func
            captured_func = f
            return f

        mock_decorator.return_value = capture_decorated

        platform_ctx = {"tenant_name": "test-tenant", "k8s_namespace": "default"}

        with patch("dcaf.core.adapters.outbound.agno.adapter.agno_tool_decorator", mock_decorator):
            from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

            adapter = AgnoAdapter(model_id="test", provider="bedrock")
            adapter._convert_tools_to_agno([mock_tool_with_context], platform_context=platform_ctx)

            # The captured function should be the wrapper
            assert captured_func is not None, "Decorator should have captured a function"

            # Call the wrapper WITHOUT platform_context - it should be injected
            result = captured_func(query="test query")

            # Verify the context was injected
            assert "test-tenant" in result, (
                f"Expected platform_context to be injected. Got: {result}"
            )

    def test_wrapper_preserves_signature_without_platform_context(self, mock_tool_with_context):
        """
        Verify that the wrapper's signature excludes platform_context.

        This is critical for Agno to infer the correct parameter schema.
        """
        mock_decorator = MagicMock()
        captured_func = None

        def capture_decorated(f):
            nonlocal captured_func
            captured_func = f
            return f

        mock_decorator.return_value = capture_decorated

        platform_ctx = {"tenant_name": "test-tenant"}

        with patch("dcaf.core.adapters.outbound.agno.adapter.agno_tool_decorator", mock_decorator):
            from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

            adapter = AgnoAdapter(model_id="test", provider="bedrock")
            adapter._convert_tools_to_agno([mock_tool_with_context], platform_context=platform_ctx)

            assert captured_func is not None

            # Get the signature of the wrapper
            sig = inspect.signature(captured_func)
            param_names = list(sig.parameters.keys())

            # platform_context should NOT be in the signature
            assert "platform_context" not in param_names, (
                f"platform_context should be removed from signature. Got parameters: {param_names}"
            )

            # But 'query' should still be there
            assert "query" in param_names, f"Expected 'query' parameter. Got: {param_names}"


# =============================================================================
# Test: Tool Schema Extraction
# =============================================================================


class TestToolSchemaExtraction:
    """Tests for extracting tool schemas."""

    def test_tool_schema_includes_input_schema(self, mock_tool):
        """Verify tool schema is extracted with input_schema."""
        from dcaf.core.adapters.outbound.agno.tool_converter import AgnoToolConverter

        converter = AgnoToolConverter()
        schema = converter.to_agno(mock_tool)

        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema

        # Verify the input_schema has the expected structure
        input_schema = schema["input_schema"]
        assert input_schema.get("type") == "object"
        assert "properties" in input_schema
        assert "message" in input_schema["properties"]
        assert "count" in input_schema["properties"]

    def test_tool_converter_does_not_return_parameters_key(self, mock_tool):
        """
        Verify the tool converter uses 'input_schema', not 'parameters'.

        The to_agno method should return a schema with 'input_schema',
        NOT 'parameters', to avoid confusion with the Agno decorator bug.
        """
        from dcaf.core.adapters.outbound.agno.tool_converter import AgnoToolConverter

        converter = AgnoToolConverter()
        schema = converter.to_agno(mock_tool)

        # Should use input_schema, not parameters
        assert "input_schema" in schema, "Expected 'input_schema' in schema"
        # 'parameters' should only be in to_agno_function, not to_agno
        # (and even there it's just for internal representation, not Agno decorator)


# =============================================================================
# Test: Multiple Tools Conversion
# =============================================================================


class TestMultipleToolsConversion:
    """Tests for converting multiple tools."""

    def test_convert_multiple_tools(self, mock_tool, mock_tool_with_context):
        """Verify multiple tools can be converted without errors."""
        mock_decorator = MagicMock()
        mock_decorator.return_value = lambda f: f

        with patch("dcaf.core.adapters.outbound.agno.adapter.agno_tool_decorator", mock_decorator):
            from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

            adapter = AgnoAdapter(model_id="test", provider="bedrock")

            tools = [mock_tool, mock_tool_with_context]
            platform_ctx = {"tenant_name": "multi-test"}

            agno_tools = adapter._convert_tools_to_agno(tools, platform_context=platform_ctx)

            assert len(agno_tools) == 2, f"Expected 2 tools, got {len(agno_tools)}"

            # Verify decorator was called twice
            assert mock_decorator.call_count == 2

            # Verify NEITHER call had 'parameters'
            for call_obj in mock_decorator.call_args_list:
                call_kwargs = call_obj.kwargs
                assert "parameters" not in call_kwargs, f"'parameters' found in call: {call_kwargs}"


# =============================================================================
# Integration Test: Full Tool Lifecycle
# =============================================================================


class TestToolLifecycle:
    """Integration tests for the full tool conversion lifecycle."""

    def test_tool_executes_after_conversion(self, mock_tool):
        """
        Verify a tool still executes correctly after conversion.

        Even though we're testing the conversion, we want to make sure
        the converted tool is still callable.
        """

        # Create a simple pass-through decorator (simulating Agno)
        def simple_decorator(**kwargs):
            def decorator(func):
                func._agno_name = kwargs.get("name")
                func._agno_description = kwargs.get("description")
                return func

            return decorator

        with patch(
            "dcaf.core.adapters.outbound.agno.adapter.agno_tool_decorator", simple_decorator
        ):
            from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

            adapter = AgnoAdapter(model_id="test", provider="bedrock")
            agno_tools = adapter._convert_tools_to_agno([mock_tool])

            assert len(agno_tools) == 1
            converted_tool = agno_tools[0]

            # The tool should be callable
            result = converted_tool(message="Hello", count=3)
            assert result == "HelloHelloHello"

            # And should have the Agno metadata
            assert converted_tool._agno_name == "echo_tool"
            assert converted_tool._agno_description == "Test tool that echoes input"


# =============================================================================
# Regression Test: The Specific Bug
# =============================================================================


class TestParametersBugRegression:
    """
    Regression tests specifically for the 'parameters' bug.

    Bug: "Invalid tool configuration arguments: {'parameters'}"

    This test class ensures the bug doesn't come back.
    """

    def test_no_parameters_in_decorator_call(self):
        """
        REGRESSION TEST: Ensure 'parameters' is never passed to Agno.

        This is the specific bug that was reported:
        - Agno's @tool decorator does NOT accept 'parameters'
        - We were incorrectly passing 'parameters=tool_schema["input_schema"]'
        - This caused: "Invalid tool configuration arguments: {'parameters'}"
        """
        from dcaf.tools import tool

        @tool(description="Regression test tool")
        def test_func(arg1: str, arg2: int = 42) -> str:
            return f"{arg1}-{arg2}"

        # Track what gets passed to the decorator
        decorator_calls = []

        def tracking_decorator(**kwargs):
            decorator_calls.append(kwargs)
            return lambda f: f

        with patch(
            "dcaf.core.adapters.outbound.agno.adapter.agno_tool_decorator", tracking_decorator
        ):
            from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

            adapter = AgnoAdapter(model_id="test", provider="bedrock")
            adapter._convert_tools_to_agno([test_func])

        # Verify calls were made
        assert len(decorator_calls) == 1, "Expected one decorator call"

        # THE CRITICAL ASSERTION
        kwargs = decorator_calls[0]
        assert "parameters" not in kwargs, (
            "REGRESSION: 'parameters' is being passed to agno_tool_decorator again!\n"
            f"Kwargs: {kwargs}\n"
            "This will cause: 'Invalid tool configuration arguments: {'parameters'}'"
        )

    def test_source_code_does_not_contain_parameters_arg(self):
        """
        Static analysis: verify the source code doesn't pass 'parameters'.

        This is a belt-and-suspenders check that reads the actual source.
        """
        import re
        from pathlib import Path

        adapter_path = Path(__file__).parent.parent / "dcaf/core/adapters/outbound/agno/adapter.py"

        if not adapter_path.exists():
            pytest.skip(f"Could not find adapter.py at {adapter_path}")

        source = adapter_path.read_text()

        # Look for the pattern: agno_tool_decorator(...parameters=...)
        # We want to make sure this pattern does NOT exist
        bad_pattern = r"agno_tool_decorator\s*\([^)]*parameters\s*="

        matches = re.findall(bad_pattern, source)

        assert not matches, (
            f"REGRESSION: Found 'parameters=' in agno_tool_decorator call!\n"
            f"Matches: {matches}\n"
            "This will cause: 'Invalid tool configuration arguments: {'parameters'}'"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
