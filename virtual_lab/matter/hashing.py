import hashlib
import json
from typing import Any

def deterministic_hash(data: Any) -> str:
    """Generate a SHA-256 hash from a deterministic JSON serialization."""
    serialized = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()
