"""Tests for Session management (dcaf.core.session)."""

from dataclasses import dataclass

import pytest

from dcaf.core.session import Session, _deserialize_value, _serialize_value

# =============================================================================
# Helper types for testing serialization
# =============================================================================


@dataclass
class SampleDataclass:
    name: str
    value: int


# We avoid importing pydantic at module level since it may not be installed.
# The Pydantic tests use a try/except guard.
try:
    from pydantic import BaseModel

    class SamplePydanticModel(BaseModel):
        name: str
        count: int = 0

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


# =============================================================================
# Session Basic Operations
# =============================================================================


class TestSessionGetSet:
    def test_set_and_get_string(self):
        session = Session()
        session.set("name", "Alice")
        assert session.get("name") == "Alice"

    def test_set_and_get_int(self):
        session = Session()
        session.set("count", 42)
        assert session.get("count") == 42

    def test_set_and_get_dict(self):
        session = Session()
        session.set("config", {"debug": True, "level": 3})
        assert session.get("config") == {"debug": True, "level": 3}

    def test_set_and_get_list(self):
        session = Session()
        session.set("items", [1, 2, 3])
        assert session.get("items") == [1, 2, 3]

    def test_set_and_get_none(self):
        session = Session()
        session.set("empty", None)
        assert session.get("empty") is None

    def test_get_missing_key_returns_none(self):
        session = Session()
        assert session.get("nonexistent") is None

    def test_get_missing_key_returns_default(self):
        session = Session()
        assert session.get("nonexistent", "fallback") == "fallback"

    def test_get_missing_key_returns_default_int(self):
        session = Session()
        assert session.get("count", 0) == 0

    def test_set_overwrites_existing(self):
        session = Session()
        session.set("key", "old")
        session.set("key", "new")
        assert session.get("key") == "new"


# =============================================================================
# Session Delete and Clear
# =============================================================================


class TestSessionDeleteClear:
    def test_delete_existing_key(self):
        session = Session()
        session.set("key", "value")
        session.delete("key")
        assert session.get("key") is None

    def test_delete_missing_key_does_not_raise(self):
        session = Session()
        session.delete("nonexistent")  # should not raise

    def test_clear_removes_all(self):
        session = Session()
        session.set("a", 1)
        session.set("b", 2)
        session.clear()
        assert session.is_empty
        assert len(session) == 0

    def test_clear_empty_session(self):
        session = Session()
        session.clear()  # should not raise
        assert session.is_empty


# =============================================================================
# Session has / keys / items / len / contains
# =============================================================================


class TestSessionUtilities:
    def test_has_existing_key(self):
        session = Session()
        session.set("key", "value")
        assert session.has("key")

    def test_has_missing_key(self):
        session = Session()
        assert not session.has("missing")

    def test_keys(self):
        session = Session()
        session.set("a", 1)
        session.set("b", 2)
        assert sorted(session.keys()) == ["a", "b"]

    def test_items(self):
        session = Session()
        session.set("x", 10)
        items = dict(session.items())
        assert items == {"x": 10}

    def test_len(self):
        session = Session()
        assert len(session) == 0
        session.set("a", 1)
        assert len(session) == 1

    def test_contains(self):
        session = Session()
        session.set("key", "value")
        assert "key" in session
        assert "missing" not in session


# =============================================================================
# Bracket Access
# =============================================================================


class TestSessionBracketAccess:
    def test_getitem(self):
        session = Session()
        session.set("key", "value")
        assert session["key"] == "value"

    def test_getitem_missing_raises_keyerror(self):
        session = Session()
        with pytest.raises(KeyError):
            _ = session["missing"]

    def test_setitem(self):
        session = Session()
        session["key"] = "value"
        assert session.get("key") == "value"

    def test_delitem(self):
        session = Session()
        session.set("key", "value")
        del session["key"]
        assert "key" not in session


# =============================================================================
# Session Modification Tracking
# =============================================================================


class TestSessionModification:
    def test_new_session_not_modified(self):
        session = Session()
        assert not session.is_modified

    def test_set_marks_modified(self):
        session = Session()
        session.set("key", "value")
        assert session.is_modified

    def test_delete_marks_modified(self):
        session = Session()
        session.set("key", "value")
        # Reset by creating new session from dict
        session2 = Session.from_dict(session.to_dict())
        assert not session2.is_modified
        session2.delete("key")
        assert session2.is_modified

    def test_clear_marks_modified(self):
        session = Session()
        session.set("key", "value")
        session2 = Session.from_dict(session.to_dict())
        session2.clear()
        assert session2.is_modified

    def test_update_marks_modified(self):
        session = Session()
        session.update({"a": 1, "b": 2})
        assert session.is_modified

    def test_bracket_set_marks_modified(self):
        session = Session()
        session["key"] = "value"
        assert session.is_modified


# =============================================================================
# Session Serialization (to_dict / from_dict)
# =============================================================================


class TestSessionSerialization:
    def test_to_dict_empty(self):
        session = Session()
        assert session.to_dict() == {}

    def test_to_dict_with_data(self):
        session = Session()
        session.set("name", "Alice")
        session.set("count", 5)
        result = session.to_dict()
        assert result == {"name": "Alice", "count": 5}

    def test_from_dict_none(self):
        session = Session.from_dict(None)
        assert session.is_empty

    def test_from_dict_empty(self):
        session = Session.from_dict({})
        assert session.is_empty

    def test_from_dict_with_data(self):
        session = Session.from_dict({"key": "value", "num": 42})
        assert session.get("key") == "value"
        assert session.get("num") == 42

    def test_from_dict_does_not_modify_original(self):
        original = {"key": "value"}
        session = Session.from_dict(original)
        session.set("new_key", "new_value")
        assert "new_key" not in original

    def test_roundtrip(self):
        session = Session()
        session.set("a", 1)
        session.set("b", [1, 2, 3])
        session.set("c", {"nested": True})

        data = session.to_dict()
        restored = Session.from_dict(data)

        assert restored.get("a") == 1
        assert restored.get("b") == [1, 2, 3]
        assert restored.get("c") == {"nested": True}


# =============================================================================
# Session update()
# =============================================================================


class TestSessionUpdate:
    def test_update_adds_multiple_keys(self):
        session = Session()
        session.update({"a": 1, "b": 2, "c": 3})
        assert session.get("a") == 1
        assert session.get("b") == 2
        assert session.get("c") == 3

    def test_update_empty_dict(self):
        session = Session()
        session.update({})
        assert not session.is_modified

    def test_update_overwrites_existing(self):
        session = Session()
        session.set("a", 1)
        session.update({"a": 99})
        assert session.get("a") == 99


# =============================================================================
# Dataclass Serialization
# =============================================================================


class TestDataclassSerialization:
    def test_serialize_dataclass(self):
        obj = SampleDataclass(name="test", value=42)
        result = _serialize_value(obj)
        assert result == {"name": "test", "value": 42}

    def test_session_stores_dataclass_as_dict(self):
        session = Session()
        session.set("item", SampleDataclass(name="test", value=5))
        raw = session.get("item")
        assert isinstance(raw, dict)
        assert raw == {"name": "test", "value": 5}

    def test_session_deserializes_dataclass(self):
        session = Session()
        session.set("item", SampleDataclass(name="test", value=5))
        item = session.get("item", as_type=SampleDataclass)
        assert isinstance(item, SampleDataclass)
        assert item.name == "test"
        assert item.value == 5


# =============================================================================
# Pydantic Serialization
# =============================================================================


@pytest.mark.skipif(not HAS_PYDANTIC, reason="pydantic not installed")
class TestPydanticSerialization:
    def test_serialize_pydantic_model(self):
        obj = SamplePydanticModel(name="test", count=3)
        result = _serialize_value(obj)
        assert result == {"name": "test", "count": 3}

    def test_session_stores_pydantic_as_dict(self):
        session = Session()
        session.set("model", SamplePydanticModel(name="hello", count=7))
        raw = session.get("model")
        assert isinstance(raw, dict)
        assert raw == {"name": "hello", "count": 7}

    def test_session_deserializes_pydantic_model(self):
        session = Session()
        session.set("model", SamplePydanticModel(name="hello", count=7))
        model = session.get("model", as_type=SamplePydanticModel)
        assert isinstance(model, SamplePydanticModel)
        assert model.name == "hello"
        assert model.count == 7


# =============================================================================
# Deserialize edge cases
# =============================================================================


class TestDeserializeEdgeCases:
    def test_deserialize_none_data_returns_none(self):
        result = _deserialize_value(None, SampleDataclass)
        assert result is None

    def test_deserialize_no_type_returns_raw(self):
        result = _deserialize_value({"a": 1}, None)
        assert result == {"a": 1}

    def test_deserialize_primitive_type_returns_raw(self):
        result = _deserialize_value(42, int)
        assert result == 42

    def test_deserialize_dataclass_bad_data_returns_raw(self):
        # If the dict keys don't match the dataclass, return raw data
        result = _deserialize_value({"wrong": "keys"}, SampleDataclass)
        assert result == {"wrong": "keys"}


# =============================================================================
# Session is_empty
# =============================================================================


class TestSessionIsEmpty:
    def test_new_session_is_empty(self):
        session = Session()
        assert session.is_empty

    def test_session_with_data_not_empty(self):
        session = Session()
        session.set("key", "value")
        assert not session.is_empty

    def test_session_empty_after_clear(self):
        session = Session()
        session.set("key", "value")
        session.clear()
        assert session.is_empty
