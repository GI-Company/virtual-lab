"""Versioned canonical encodings. New signatures use RFC 8785 (JCS).

Historical Python encodings are verification-only: never rehash persisted events
or silently promote a legacy signature to the current signing scheme.
"""
import json
from typing import Any
import rfc8785


def canonical_json(data: Any) -> bytes:
    return rfc8785.dumps(data)


def legacy_canonical_json(data: Any, *, normalize_zero: bool = True) -> bytes:
    def normalize(value):
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(v) for v in value]
        if normalize_zero and isinstance(value, float) and value == 0.0:
            return 0.0
        return value
    return json.dumps(normalize(data), separators=(',', ':'), sort_keys=True,
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def strict_json_loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON value: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
