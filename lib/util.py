from types import SimpleNamespace
import json

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
    if isinstance(obj, SafeNamespace):
        return {k: from_obj(v) for k, v in vars(obj).items()}
    elif isinstance(obj, list):
        return [from_obj(item) for item in obj]
    return obj

def dump_json(file, data, **kwargs):
    file.parent.mkdir(parents=True, exist_ok=True)
    return file.write_text(json.dumps(
        data,
        default=vars,  # Handles SimpleNamespace
        indent=2,      # Default pretty printing
        **kwargs,
    ))
