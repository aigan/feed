from __future__ import annotations

import json
from types import SimpleNamespace


class SafeNamespace(SimpleNamespace):
    def __getattr__(self, name):
        # Return a special "NoneObject" for missing attributes
        return NoneObject()

class NoneObject:
    # This object acts like None but can be accessed with dot notation
    def __getattr__(self, name):
        return self

    def __bool__(self):
        return False

    # Make it behave like None in comparisons
    def __eq__(self, other):
        return other is None

    # Make it convertible to string, etc.
    def __str__(self):
        return "None"

    def __repr__(self):
        return "None"

def to_obj(d):
    if isinstance(d, dict):
        return SafeNamespace(**{k: to_obj(v) for k, v in d.items()})
    elif isinstance(d, list):
        return [to_obj(i) for i in d]
    return d

def from_obj(obj):
    if isinstance(obj, NoneObject):
        return None
    if isinstance(obj, SafeNamespace):
        return {k: from_obj(v) for k, v in vars(obj).items()}
    elif isinstance(obj, list):
        return [from_obj(item) for item in obj]
    return obj

def to_dict(data):
    result = {}
    for key in data.keys():
        result[key] = from_obj(data.get(key))
    return result

def safe_convert(converter_func):
    """Decorator that handles None or empty string inputs"""
    def wrapper(value):
        if (value is None
            or (isinstance(value, str) and value.strip() == '')
            or (hasattr(value, '__class__') and value.__class__.__name__ == 'NoneObject')
            #or (hasattr(value, '__bool__') and not bool(value))
            ):
            return None
        return converter_func(value)
    return wrapper

from datetime import datetime

TYPE_CONVERTERS = {
    datetime: safe_convert(datetime.fromisoformat),
    int: safe_convert(int),
    #float: safe_convert(float),
    bool: safe_convert(lambda v: str(v).lower() in ('true', 'yes', '1', 'on') if isinstance(v, str) else bool(v)),
}

def convert_fields(cls, data: Dict[str, Any]) -> Dict[str, Any]:
    from typing import Any, Callable, Dict, Optional, Union, get_args, get_origin, get_type_hints  # noqa: I001
    """
    Convert fields in data according to their types in the class.
    Handles both direct types and Optional[Type] annotations.
    """
    result = data.copy()
    type_hints = get_type_hints(cls)

    for field_name, field_type in type_hints.items():
        if field_name not in result:
            continue

        base_types = []
        origin = get_origin(field_type)

        if origin is Union or origin is Optional:
            base_types = [t for t in get_args(field_type) if t is not type(None)]
        else:
            base_types = [field_type]

        for base_type in base_types:
            if base_type in TYPE_CONVERTERS:
                result[field_name] = TYPE_CONVERTERS[base_type](result[field_name])
                break

    return result

def to_serializable(obj):
    """Convert Python objects to JSON-serializable types."""
    from dataclasses import asdict, is_dataclass

    if is_dataclass(obj):
        # Convert dataclass to dict
        obj_dict = asdict(obj)
        # Process the dict to handle nested objects
        return {k: to_serializable(v) for k, v in obj_dict.items()}

    if hasattr(obj, 'isoformat'):  # Handle datetime objects
        return obj.isoformat()

    if isinstance(obj, dict):
        # Handle dictionaries with non-serializable values
        return {k: to_serializable(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        # Handle lists and tuples
        return [to_serializable(item) for item in obj]

    # Return other primitive types as is
    return obj

def dump_json(file, data, **kwargs):
    file.parent.mkdir(parents=True, exist_ok=True)
    return file.write_text(json.dumps(
        data,
        default=vars,
        indent=2,
        **kwargs,
    ))
