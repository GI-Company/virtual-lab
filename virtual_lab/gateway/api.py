"""
virtual_lab.gateway.api
───────────────────────
High-level public Python API for the Virtual Lab Tool Gateway.
Allows direct execution from Python code, Vertex AI agent clients, or CLI scripts.
"""

from typing import Dict, Any, Optional
from virtual_lab.gateway.engine import GatewayEngine
from virtual_lab.gateway.models import ToolResponse

_DEFAULT_ENGINE: Optional[GatewayEngine] = None


def get_default_engine() -> GatewayEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = GatewayEngine()
    return _DEFAULT_ENGINE


def device_list(requesting_agent: Optional[str] = None) -> ToolResponse:
    """Discover all hardware instruments and SensorNode devices known to Virtual Lab."""
    return get_default_engine().execute_tool(
        tool_name="device.list",
        arguments={},
        requesting_agent=requesting_agent
    )


def device_describe(device_id: str, requesting_agent: Optional[str] = None) -> ToolResponse:
    """Retrieve factual specifications and capabilities of a known Virtual Lab hardware device."""
    return get_default_engine().execute_tool(
        tool_name="device.describe",
        arguments={"device_id": device_id},
        requesting_agent=requesting_agent
    )


def device_status(device_id: str, requesting_agent: Optional[str] = None) -> ToolResponse:
    """Query live connectivity and diagnostic status for a hardware device."""
    return get_default_engine().execute_tool(
        tool_name="device.status",
        arguments={"device_id": device_id},
        requesting_agent=requesting_agent
    )


def device_calibration_get(device_id: str, requesting_agent: Optional[str] = None) -> ToolResponse:
    """Retrieve verified calibration metadata for a device."""
    return get_default_engine().execute_tool(
        tool_name="device.calibration.get",
        arguments={"device_id": device_id},
        requesting_agent=requesting_agent
    )
