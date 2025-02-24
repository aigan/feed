from types import SimpleNamespace
import json

def to_obj(d):
    if isinstance(d, dict):
        return SimpleNamespace(**{k: to_obj(v) for k, v in d.items()})
    elif isinstance(d, list):
        return [to_obj(i) for i in d]
    return d

def dump_json(data, **kwargs):
    return json.dumps(data, 
                     default=vars,  # Handles SimpleNamespace
                     indent=2,      # Default pretty printing
                     **kwargs)      # Allow overriding defaults
