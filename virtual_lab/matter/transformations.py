from dataclasses import dataclass
from typing import Any, Dict
import datetime

@dataclass(frozen=True)
class ProvenanceEvent:
    parent_hash: str
    operation: str
    engine: str
    engine_version: str
    parameters: Dict[str, Any]
    timestamp: str
    output_hash: str

def create_provenance_event(parent_hash: str, output_hash: str, operation: str, engine: str, parameters: Dict[str, Any]) -> ProvenanceEvent:
    return ProvenanceEvent(
        parent_hash=parent_hash,
        operation=operation,
        engine=engine,
        engine_version="0.1",
        parameters=parameters,
        timestamp=datetime.datetime.utcnow().isoformat(),
        output_hash=output_hash
    )
