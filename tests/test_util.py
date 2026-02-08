from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from util import (
    NoneObject,
    SafeNamespace,
    convert_fields,
    from_obj,
    to_obj,
    to_serializable,
)

# --- SafeNamespace / NoneObject ---

class TestSafeNamespace:
    def test_existing_attribute(self):
        ns = SafeNamespace(name="alice", age=30)
        assert ns.name == "alice"
        assert ns.age == 30

    def test_missing_attribute_returns_none_object(self):
        ns = SafeNamespace(name="alice")
        result = ns.missing
        assert isinstance(result, NoneObject)

    def test_missing_attribute_is_falsy(self):
        ns = SafeNamespace()
        assert not ns.anything

    def test_chained_missing_attributes(self):
        ns = SafeNamespace()
        result = ns.a.b.c
        assert isinstance(result, NoneObject)
        assert not result


class TestNoneObject:
    def test_bool_is_false(self):
        assert not NoneObject()

    def test_eq_none(self):
        assert NoneObject() == None  # noqa: E711

    def test_str(self):
        assert str(NoneObject()) == "None"

    def test_repr(self):
        assert repr(NoneObject()) == "None"

    def test_getattr_returns_self(self):
        n = NoneObject()
        assert isinstance(n.foo, NoneObject)
        assert isinstance(n.foo.bar, NoneObject)


# --- to_obj / from_obj round-trip ---

class TestToObjFromObj:
    def test_simple_dict(self):
        d = {"x": 1, "y": "hello"}
        obj = to_obj(d)
        assert obj.x == 1
        assert obj.y == "hello"

    def test_nested_dict(self):
        d = {"outer": {"inner": 42}}
        obj = to_obj(d)
        assert obj.outer.inner == 42

    def test_list_of_dicts(self):
        d = {"items": [{"a": 1}, {"a": 2}]}
        obj = to_obj(d)
        assert obj.items[0].a == 1
        assert obj.items[1].a == 2

    def test_round_trip(self):
        original = {"name": "test", "nested": {"key": "val"}, "items": [1, 2, 3]}
        obj = to_obj(original)
        result = from_obj(obj)
        assert result == original

    def test_from_obj_none_object(self):
        assert from_obj(NoneObject()) is None

    def test_from_obj_list(self):
        ns = SafeNamespace(a=1)
        result = from_obj([ns, 42, "str"])
        assert result == [{"a": 1}, 42, "str"]

    def test_primitives_pass_through(self):
        assert to_obj(42) == 42
        assert to_obj("hello") == "hello"
        assert from_obj(42) == 42


# --- convert_fields ---

class TestConvertFields:
    def test_datetime_conversion(self):
        @dataclass
        class Item:
            created: datetime

        data = {"created": "2024-06-15T10:30:00+00:00"}
        result = convert_fields(Item, data)
        assert isinstance(result["created"], datetime)
        assert result["created"].year == 2024

    def test_int_conversion(self):
        @dataclass
        class Item:
            count: int

        data = {"count": "42"}
        result = convert_fields(Item, data)
        assert result["count"] == 42
        assert isinstance(result["count"], int)

    def test_bool_conversion_from_string(self):
        @dataclass
        class Item:
            active: bool

        for true_val in ("true", "True", "yes", "1", "on"):
            result = convert_fields(Item, {"active": true_val})
            assert result["active"] is True, f"Failed for {true_val!r}"

        for false_val in ("false", "no", "0", "off"):
            result = convert_fields(Item, {"active": false_val})
            assert result["active"] is False, f"Failed for {false_val!r}"

    def test_none_stays_none(self):
        @dataclass
        class Item:
            created: Optional[datetime] = None
            count: Optional[int] = None

        result = convert_fields(Item, {"created": None, "count": None})
        assert result["created"] is None
        assert result["count"] is None

    def test_empty_string_stays_none(self):
        @dataclass
        class Item:
            count: Optional[int] = None

        result = convert_fields(Item, {"count": ""})
        assert result["count"] is None

    def test_extra_fields_preserved(self):
        @dataclass
        class Item:
            name: str

        data = {"name": "test", "extra": "stuff"}
        result = convert_fields(Item, data)
        assert result["extra"] == "stuff"

    def test_missing_fields_ignored(self):
        @dataclass
        class Item:
            name: str
            age: int

        data = {"name": "test"}
        result = convert_fields(Item, data)
        assert result == {"name": "test"}


# --- to_serializable ---

class TestToSerializable:
    def test_dataclass(self):
        @dataclass
        class Item:
            name: str
            count: int

        result = to_serializable(Item(name="test", count=5))
        assert result == {"name": "test", "count": 5}

    def test_datetime(self):
        dt = datetime(2024, 6, 15, 10, 30, 0)
        assert to_serializable(dt) == "2024-06-15T10:30:00"

    def test_nested_dataclass_with_datetime(self):
        @dataclass
        class Inner:
            ts: datetime

        @dataclass
        class Outer:
            inner: Inner
            label: str

        obj = Outer(inner=Inner(ts=datetime(2024, 1, 1)), label="x")
        result = to_serializable(obj)
        assert result == {"inner": {"ts": "2024-01-01T00:00:00"}, "label": "x"}

    def test_dict(self):
        d = {"dt": datetime(2024, 1, 1), "n": 42}
        result = to_serializable(d)
        assert result == {"dt": "2024-01-01T00:00:00", "n": 42}

    def test_list(self):
        result = to_serializable([datetime(2024, 1, 1), 42, "x"])
        assert result == ["2024-01-01T00:00:00", 42, "x"]

    def test_primitives(self):
        assert to_serializable(42) == 42
        assert to_serializable("hello") == "hello"
        assert to_serializable(None) is None
