"""
virtual_lab.gateway.models
──────────────────────────
Common response contracts and data models for Virtual Lab Gateway tools.
Strictly adheres to the vlab.tool.v1 schema specification.
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field


class ToolState(str, Enum):
    PROPOSED = "PROPOSED"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    CANCELLED = "CANCELLED"


class EvidenceItem(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    evidence_type: str = "INSTRUMENT_TELEMETRY"
    source_id: str
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    artifact_uri: Optional[str] = None
    sha256: Optional[str] = None


class ToolError(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ToolResponse(BaseModel):
    schema_version: str = "vlab.tool.v1"
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool: str
    state: ToolState
    created_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence: List[EvidenceItem] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)
    errors: List[ToolError] = Field(default_factory=list)
