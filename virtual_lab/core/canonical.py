"""
virtual_lab.core.canonical
──────────────────────────
Implements RFC 8785 (JCS) style Canonical JSON serialization.
Used universally across VirtualLab to ensure predictable hashing for:
- Proposals
- Ed25519 signatures
- Genesis payloads
- Manifests
"""

import json
from typing import Any

def _normalize_numbers(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize_numbers(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_numbers(v) for v in value]
    if isinstance(value, float) and value == 0.0:
        return 0.0
    return value


def canonical_json(data: Any) -> bytes:
    """
    Returns RFC 8785 / JCS style canonical JSON representation as UTF-8 bytes.
    Ensures that identical objects hash to the exact same bytes regardless of 
    language or environment runtime dictionaries.
    """
    # separators=(',', ':') removes whitespace
    # sort_keys=True enforces alphabetical key ordering
    # ensure_ascii=False allows literal UTF-8
    # allow_nan=False rejects non-standard JSON floats (NaN, Infinity)
    normalized = _normalize_numbers(data)
    serialized = json.dumps(
        normalized, 
        separators=(',', ':'), 
        sort_keys=True, 
        ensure_ascii=False, 
        allow_nan=False
    )
    return serialized.encode('utf-8')
