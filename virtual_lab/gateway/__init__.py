"""
virtual_lab.gateway
───────────────────
Virtual Lab Tool Gateway.
Provides a strict, authoritative tool/API boundary between Vertex AI multi-agent systems
and the actual Virtual Lab laboratory environment.
"""

from virtual_lab.gateway.models import (
    ToolState,
    ToolResponse,
    ToolError,
    EvidenceItem,
)
from virtual_lab.gateway.providers.base import DeviceProvider
from virtual_lab.gateway.providers.sensornode import SensorNodeProvider
from virtual_lab.gateway.device_service import DeviceService, DeviceNotFoundError, InvalidDeviceIdError
from virtual_lab.gateway.engine import GatewayEngine
from virtual_lab.gateway.mcp_adapter import MCPAdapter
from virtual_lab.gateway.api import (
    device_list,
    device_describe,
    device_status,
    device_calibration_get,
    get_default_engine,
)

__all__ = [
    "ToolState",
    "ToolResponse",
    "ToolError",
    "EvidenceItem",
    "DeviceProvider",
    "SensorNodeProvider",
    "DeviceService",
    "DeviceNotFoundError",
    "InvalidDeviceIdError",
    "GatewayEngine",
    "MCPAdapter",
    "device_list",
    "device_describe",
    "device_status",
    "device_calibration_get",
    "get_default_engine",
]
