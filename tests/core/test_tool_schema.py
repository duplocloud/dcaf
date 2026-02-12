"""Tests for tool schema normalization — Pydantic model, raw dict, and full spec support."""

import pytest
from pydantic import BaseModel, Field

from dcaf.tools import Tool, _normalize_schema, create_tool, tool

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class TerminalCommandInput(BaseModel):
    command: str = Field(..., description="Complete terminal command")
    explanation: str = Field(..., description="What this command does")


class WeatherInput(BaseModel):
    city: str = Field(..., description="City name")
    units: str = Field(default="celsius", description="Temperature units")


RAW_SCHEMA = {
    "type": "object",
    "properties": {
        "x": {"type": "string", "description": "Input value"},
    },
    "required": ["x"],
}

FULL_SPEC = {
    "name": "my_tool",
    "description": "A test tool",
    "input_schema": {
        "type": "object",
        "properties": {"x": {"type": "string", "description": "Input value"}},
        "required": ["x"],
    },
}


def _dummy(x: str) -> str:
    return x


# ---------------------------------------------------------------------------
# _normalize_schema
# ---------------------------------------------------------------------------


class TestNormalizeSchema:
    """Tests for the _normalize_schema helper."""

    def test_pydantic_model_class(self):
        result = _normalize_schema(WeatherInput, "get_weather", "Get weather")
        assert result["name"] == "get_weather"
        assert result["description"] == "Get weather"
        assert "properties" in result["input_schema"]
        assert "city" in result["input_schema"]["properties"]
        assert "units" in result["input_schema"]["properties"]

    def test_raw_json_schema_dict(self):
        result = _normalize_schema(RAW_SCHEMA, "my_tool", "A test tool")
        assert result["name"] == "my_tool"
        assert result["description"] == "A test tool"
        assert result["input_schema"] is RAW_SCHEMA

    def test_full_anthropic_spec_passthrough(self):
        result = _normalize_schema(FULL_SPEC, "ignored", "ignored")
        assert result is FULL_SPEC

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError, match="schema must be a dict or Pydantic BaseModel class"):
            _normalize_schema(42, "t", "d")


# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------


class TestToolDecoratorSchemaFormats:
    """Tests that @tool accepts all three schema formats."""

    def test_pydantic_model(self):
        @tool(schema=TerminalCommandInput, requires_approval=True)
        def execute_terminal_cmd(command: str, explanation: str) -> str:
            """Execute a terminal command."""
            return "done"

        assert isinstance(execute_terminal_cmd, Tool)
        schema = execute_terminal_cmd.get_schema()
        assert schema["name"] == "execute_terminal_cmd"
        assert schema["description"] == "Execute a terminal command."
        assert "command" in schema["input_schema"]["properties"]
        assert "explanation" in schema["input_schema"]["properties"]

    def test_raw_json_schema(self):
        @tool(
            schema={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                },
                "required": ["location"],
            }
        )
        def get_weather(location: str) -> str:
            """Get weather for a city."""
            return f"Weather in {location}: Sunny"

        schema = get_weather.get_schema()
        assert schema["name"] == "get_weather"
        assert schema["description"] == "Get weather for a city."
        assert schema["input_schema"]["properties"]["location"]["type"] == "string"

    def test_full_anthropic_spec(self):
        @tool(
            schema={
                "name": "get_weather",
                "description": "Get weather for a city",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
        )
        def get_weather(city: str) -> str:
            """Get weather for a city."""
            return f"Weather in {city}: Sunny"

        schema = get_weather.get_schema()
        assert schema["name"] == "get_weather"
        assert schema["input_schema"]["required"] == ["city"]

    def test_requires_approval_defaults_true(self):
        @tool(schema=WeatherInput)
        def get_weather(city: str) -> str:
            """Get weather."""
            return city

        assert get_weather.requires_approval is True


# ---------------------------------------------------------------------------
# create_tool
# ---------------------------------------------------------------------------


class TestCreateToolSchemaFormats:
    """Tests that create_tool accepts all three schema formats."""

    def test_pydantic_model(self):
        t = create_tool(func=_dummy, schema=WeatherInput, description="Get weather")
        schema = t.get_schema()
        assert schema["name"] == "_dummy"
        assert "city" in schema["input_schema"]["properties"]

    def test_raw_json_schema(self):
        t = create_tool(func=_dummy, schema=RAW_SCHEMA, description="A test tool")
        schema = t.get_schema()
        assert schema["input_schema"] is RAW_SCHEMA

    def test_full_spec(self):
        t = create_tool(func=_dummy, schema=FULL_SPEC)
        schema = t.get_schema()
        assert schema["name"] == "my_tool"
        assert "input_schema" in schema


# ---------------------------------------------------------------------------
# Tool.get_schema — resilience
# ---------------------------------------------------------------------------


class TestToolGetSchemaResilience:
    """get_schema() should never raise, regardless of schema format stored."""

    def test_raw_schema_stored_directly(self):
        """If a raw schema dict ends up in Tool.schema, get_schema wraps it."""
        t = Tool(
            func=_dummy,
            name="my_tool",
            description="A test tool",
            schema=RAW_SCHEMA,
        )
        schema = t.get_schema()
        assert schema["name"] == "my_tool"
        assert schema["description"] == "A test tool"
        assert schema["input_schema"] == RAW_SCHEMA

    def test_full_spec_stored_directly(self):
        t = Tool(
            func=_dummy,
            name="my_tool",
            description="A test tool",
            schema=FULL_SPEC,
        )
        schema = t.get_schema()
        assert schema["name"] == "my_tool"
        assert schema["input_schema"]["required"] == ["x"]
