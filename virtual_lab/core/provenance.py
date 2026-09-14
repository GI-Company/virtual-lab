from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

class ProvenanceRecord:
    def __init__(self, action: str, details: Dict[str, Any]):
        self.action = action
        self.details = details
        self.timestamp = datetime.now(timezone.utc).isoformat()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "timestamp": self.timestamp,
            "details": self.details
        }

class ProvenanceTracker:
    def __init__(self):
        self.history: List[ProvenanceRecord] = []

    def record(self, action: str, details: Dict[str, Any]):
        self.history.append(ProvenanceRecord(action, details))

    def generate_hash(self) -> str:
        data = [r.to_dict() for r in self.history]
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def serialize(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self.history]
