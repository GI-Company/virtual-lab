from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from virtual_lab.core.canonical import canonical_json

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
        data = self.serialize()
        return hashlib.sha256(canonical_json(data)).hexdigest()

    def generate_content_hash(self) -> str:
        """Reproducibility fingerprint; deliberately excludes acquisition time."""
        return hashlib.sha256(canonical_json([
            {"action": r.action, "details": r.details} for r in self.history])).hexdigest()

    def serialize(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self.history]
