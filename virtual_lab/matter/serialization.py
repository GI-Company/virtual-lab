import dataclasses
import numpy as np

def serialize_dataclass(obj) -> dict:
    """Recursively serialize a dataclass to a basic dict suitable for hashing and JSON."""
    if dataclasses.is_dataclass(obj):
        result = {}
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            result[f.name] = serialize_dataclass(value)
        return result
    elif isinstance(obj, (list, tuple)):
        return [serialize_dataclass(v) for v in obj]
    elif isinstance(obj, dict):
        return {k: serialize_dataclass(v) for k, v in obj.items()}
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif hasattr(obj, 'to_dict'):
        return obj.to_dict()
    else:
        return obj
