"""
virtual_lab.gateway.engine
──────────────────────────
Core execution engine for the Virtual Lab Tool Gateway.
Receives tool invocation requests, validates arguments, coordinates device services,
gathers evidence, logs audit records, and formats responses adhering to vlab.tool.v1.
"""

import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from virtual_lab.gateway.models import ToolResponse, ToolState, ToolError, EvidenceItem
from virtual_lab.gateway.device_service import DeviceService, DeviceNotFoundError, InvalidDeviceIdError

logger = logging.getLogger("virtuallab.gateway.engine")
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)


class GatewayEngine:
    PHASE1_ALLOWED_TOOLS = {
        "device.list",
        "device.describe",
        "device.status",
        "device.calibration.get"
    }

    def __init__(self, device_service: Optional[DeviceService] = None):
        self.device_service = device_service if device_service is not None else DeviceService()
        self.invocation_log = []

    def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        requesting_agent: Optional[str] = None
    ) -> ToolResponse:
        """
        Executes a gateway tool under strict read-only / L1 constraints.
        Returns a formatted ToolResponse conforming to vlab.tool.v1.
        """
        t_start = time.time()
        created_at_utc = datetime.now(timezone.utc).isoformat()
        req_id = request_id or str(uuid.uuid4())
        corr_id = correlation_id or str(uuid.uuid4())
        args = arguments or {}

        # 1. Check phase 1 permissions (Read-only discovery only)
        if tool_name not in self.PHASE1_ALLOWED_TOOLS:
            completed_at_utc = datetime.now(timezone.utc).isoformat()
            resp = ToolResponse(
                schema_version="vlab.tool.v1",
                request_id=req_id,
                correlation_id=corr_id,
                tool=tool_name,
                state=ToolState.REJECTED,
                created_at_utc=created_at_utc,
                completed_at_utc=completed_at_utc,
                evidence=[],
                payload={},
                errors=[ToolError(
                    code="TOOL_FORBIDDEN_PHASE1",
                    message=f"Tool '{tool_name}' is not permitted in Phase 1 read-only mode. Only discovery tools are allowed."
                )]
            )
            self._record_invocation(resp, requesting_agent, time.time() - t_start)
            return resp

        # 2. Dispatch tool
        evidence = []
        payload = {}
        errors = []
        state = ToolState.COMPLETED

        try:
            if tool_name == "device.list":
                devices = self.device_service.list_devices()
                payload = {"devices": devices}
                if devices:
                    evidence.append(EvidenceItem(
                        evidence_type="INSTRUMENT_DISCOVERY",
                        source_id="device_service",
                        timestamp_utc=datetime.now(timezone.utc).isoformat()
                    ))

            elif tool_name == "device.describe":
                device_id = args.get("device_id")
                if not device_id:
                    state = ToolState.FAILED
                    errors.append(ToolError(code="MISSING_ARGUMENT", message="Missing required argument 'device_id'."))
                else:
                    details = self.device_service.describe_device(device_id)
                    payload = details
                    evidence.append(EvidenceItem(
                        evidence_type="INSTRUMENT_DESCRIPTOR",
                        source_id=device_id,
                        timestamp_utc=datetime.now(timezone.utc).isoformat()
                    ))

            elif tool_name == "device.status":
                device_id = args.get("device_id")
                if not device_id:
                    state = ToolState.FAILED
                    errors.append(ToolError(code="MISSING_ARGUMENT", message="Missing required argument 'device_id'."))
                else:
                    status_info = self.device_service.get_status(device_id)
                    payload = status_info
                    evidence.append(EvidenceItem(
                        evidence_type="INSTRUMENT_TELEMETRY",
                        source_id=device_id,
                        timestamp_utc=datetime.now(timezone.utc).isoformat()
                    ))

            elif tool_name == "device.calibration.get":
                device_id = args.get("device_id")
                if not device_id:
                    state = ToolState.FAILED
                    errors.append(ToolError(code="MISSING_ARGUMENT", message="Missing required argument 'device_id'."))
                else:
                    cal_info = self.device_service.get_calibration(device_id)
                    payload = cal_info
                    # If calibration record exists, COMPLETED. If UNAVAILABLE record, state is UNAVAILABLE
                    if cal_info.get("status") == "UNAVAILABLE":
                        state = ToolState.UNAVAILABLE
                    evidence.append(EvidenceItem(
                        evidence_type="INSTRUMENT_CALIBRATION",
                        source_id=device_id,
                        timestamp_utc=datetime.now(timezone.utc).isoformat()
                    ))

        except InvalidDeviceIdError as ide:
            state = ToolState.FAILED
            errors.append(ToolError(code="INVALID_ARGUMENT", message=str(ide)))

        except DeviceNotFoundError as dne:
            state = ToolState.UNAVAILABLE
            errors.append(ToolError(code="NOT_FOUND", message=str(dne)))

        except Exception as exc:
            state = ToolState.FAILED
            errors.append(ToolError(code="DRIVER_FAILURE", message=f"Internal driver failure: {str(exc)}"))

        completed_at_utc = datetime.now(timezone.utc).isoformat()
        response = ToolResponse(
            schema_version="vlab.tool.v1",
            request_id=req_id,
            correlation_id=corr_id,
            tool=tool_name,
            state=state,
            created_at_utc=created_at_utc,
            completed_at_utc=completed_at_utc,
            evidence=evidence,
            payload=payload,
            errors=errors
        )

        self._record_invocation(response, requesting_agent, time.time() - t_start)
        return response

    def _record_invocation(self, resp: ToolResponse, agent: Optional[str], duration_s: float):
        record = {
            "request_id": resp.request_id,
            "correlation_id": resp.correlation_id,
            "tool": resp.tool,
            "timestamp_utc": resp.created_at_utc,
            "requesting_agent": agent or "unknown",
            "state": resp.state.value,
            "duration_ms": int(duration_s * 1000),
            "errors": [e.code for e in resp.errors],
            "evidence_count": len(resp.evidence)
        }
        self.invocation_log.append(record)
        logger.info("[AUDIT] tool=%s state=%s req=%s duration=%dms", resp.tool, resp.state.value, resp.request_id, record["duration_ms"])
