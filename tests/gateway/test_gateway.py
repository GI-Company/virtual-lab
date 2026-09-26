"""
tests.gateway.test_gateway
──────────────────────────
Comprehensive test suite for Virtual Lab Tool Gateway (Phase 1).
Verifies all 10 core constraints, including the Zero-Fabrication Rule,
schema compliance, error handling, and read-only isolation.
"""

import pytest
import os
import tempfile
import json
from unittest.mock import MagicMock, patch

from virtual_lab.gateway.models import ToolResponse, ToolState
from virtual_lab.gateway.providers.base import DeviceProvider
from virtual_lab.gateway.providers.sensornode import SensorNodeProvider
from virtual_lab.gateway.device_service import DeviceService, DeviceNotFoundError, InvalidDeviceIdError
from virtual_lab.gateway.engine import GatewayEngine
from virtual_lab.gateway.mcp_adapter import MCPAdapter
from virtual_lab.instruments.connection import (
    ConnectionRegistry,
    DeviceConnectionState,
    ChannelConnectionState,
    SensorChannelState,
    CameraChannelState,
    ControlChannelState,
    InstrumentState,
)


class FailingDriverProvider(DeviceProvider):
    """Test provider that simulates driver crash / hardware communication fault."""
    @property
    def name(self) -> str:
        return "failing_driver"

    def list_devices(self):
        raise ConnectionResetError("Hardware bus I/O timeout")

    def describe_device(self, device_id: str):
        if device_id == "failing-device":
            raise IOError("Hardware register read failure")
        return None

    def get_status(self, device_id: str):
        if device_id == "failing-device":
            raise TimeoutError("Device failed to acknowledge ping")
        return None

    def get_calibration(self, device_id: str):
        if device_id == "failing-device":
            raise RuntimeError("EEPROM parity error")
        return None


class MockRealProvider(DeviceProvider):
    """Controlled provider representing an actual connected instrument with known telemetry."""
    @property
    def name(self) -> str:
        return "mock_real_hardware"

    def list_devices(self):
        return [{
            "device_id": "lab-sensor-01",
            "device_type": "optical_spectrometer",
            "name": "OceanOptics HR4000",
            "connection_state": "ONLINE",
            "transport": "usb",
            "capabilities": ["spectroscopy", "uv_vis", "dark_correction"]
        }, {
            "device_id": "lab-sensor-offline",
            "device_type": "environmental_monitor",
            "name": "BME680 Sensor",
            "connection_state": "OFFLINE",
            "transport": "i2c",
            "capabilities": ["temperature", "humidity", "pressure"]
        }]

    def describe_device(self, device_id: str):
        if device_id == "lab-sensor-01":
            return {
                "device_id": "lab-sensor-01",
                "device_type": "optical_spectrometer",
                "manufacturer": "Ocean Optics",
                "model": "HR4000",
                "serial_number": "HR4-9981",
                "firmware_version": "v2.1.0",
                "transport": "usb",
                "capabilities": ["spectroscopy", "uv_vis", "dark_correction"],
                "measurement_types": ["SPECTRAL_INTENSITY"],
                "native_units": {"SPECTRAL_INTENSITY": "counts"},
                "driver_provider": self.name,
                "connection_metadata": {"bus": 1, "address": 4}
            }
        elif device_id == "lab-sensor-offline":
            return {
                "device_id": "lab-sensor-offline",
                "device_type": "environmental_monitor",
                "manufacturer": "Bosch",
                "model": "BME680",
                "serial_number": None,
                "firmware_version": None,
                "transport": "i2c",
                "capabilities": ["temperature", "humidity", "pressure"],
                "measurement_types": ["TEMPERATURE", "HUMIDITY", "PRESSURE"],
                "native_units": {"TEMPERATURE": "degC", "HUMIDITY": "%", "PRESSURE": "hPa"},
                "driver_provider": self.name,
                "connection_metadata": None
            }
        return None

    def get_status(self, device_id: str):
        if device_id == "lab-sensor-01":
            return {
                "device_id": "lab-sensor-01",
                "status": "ONLINE",
                "diagnostics": {
                    "last_seen_utc": "2026-09-19T12:00:00Z",
                    "transport_state": "usb_connected",
                    "driver_state": "READY",
                    "battery": None,
                    "error_codes": [],
                    "sensor_availability": {"spectrometer": True}
                }
            }
        elif device_id == "lab-sensor-offline":
            return {
                "device_id": "lab-sensor-offline",
                "status": "OFFLINE",
                "diagnostics": {
                    "last_seen_utc": None,
                    "transport_state": "bus_unresponsive",
                    "driver_state": "OFFLINE",
                    "battery": None,
                    "error_codes": ["ERR_NO_ACK"],
                    "sensor_availability": {"temperature": False}
                }
            }
        return None

    def get_calibration(self, device_id: str):
        if device_id == "lab-sensor-01":
            return {
                "status": "AVAILABLE",
                "calibration_data": {
                    "dark_counts": [12, 11, 13],
                    "wavelength_coefficients": [200.0, 0.25, -0.0001]
                }
            }
        elif device_id == "lab-sensor-offline":
            return {
                "status": "UNAVAILABLE",
                "reason": "NO_CALIBRATION_RECORD"
            }
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. No-device environment returns an empty list, not fake hardware.
# ─────────────────────────────────────────────────────────────────────────────

def test_1_no_device_environment_returns_empty_list():
    registry = ConnectionRegistry()
    # Mock adb returning no devices
    with patch("shutil.which", return_value="/usr/bin/adb"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="List of devices attached\n\n")

        provider = SensorNodeProvider(registry=registry)
        service = DeviceService(providers=[provider])
        engine = GatewayEngine(device_service=service)

        resp = engine.execute_tool("device.list")
        assert resp.state == ToolState.COMPLETED
        assert resp.payload == {"devices": []}
        assert resp.errors == []
        assert isinstance(resp.payload["devices"], list)
        assert len(resp.payload["devices"]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Unknown device ID returns NOT_FOUND.
# ─────────────────────────────────────────────────────────────────────────────

def test_2_unknown_device_id_returns_not_found():
    service = DeviceService(providers=[MockRealProvider()])
    engine = GatewayEngine(device_service=service)

    # describe unknown
    resp_desc = engine.execute_tool("device.describe", {"device_id": "nonexistent-device-123"})
    assert resp_desc.state == ToolState.UNAVAILABLE
    assert any(err.code == "NOT_FOUND" for err in resp_desc.errors)

    # status unknown
    resp_stat = engine.execute_tool("device.status", {"device_id": "nonexistent-device-123"})
    assert resp_stat.state == ToolState.UNAVAILABLE
    assert any(err.code == "NOT_FOUND" for err in resp_stat.errors)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Offline hardware returns OFFLINE/UNAVAILABLE.
# ─────────────────────────────────────────────────────────────────────────────

def test_3_offline_hardware_returns_offline():
    service = DeviceService(providers=[MockRealProvider()])
    engine = GatewayEngine(device_service=service)

    resp = engine.execute_tool("device.status", {"device_id": "lab-sensor-offline"})
    assert resp.state == ToolState.COMPLETED
    assert resp.payload["status"] == "OFFLINE"
    assert resp.payload["diagnostics"]["driver_state"] == "OFFLINE"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Driver failure returns FAILED.
# ─────────────────────────────────────────────────────────────────────────────

def test_4_driver_failure_returns_failed():
    service = DeviceService(providers=[FailingDriverProvider()])
    engine = GatewayEngine(device_service=service)

    resp_desc = engine.execute_tool("device.describe", {"device_id": "failing-device"})
    assert resp_desc.state == ToolState.FAILED
    assert any(err.code == "DRIVER_FAILURE" for err in resp_desc.errors)
    assert "Hardware register read failure" in resp_desc.errors[0].message

    resp_stat = engine.execute_tool("device.status", {"device_id": "failing-device"})
    assert resp_stat.state == ToolState.FAILED
    assert any(err.code == "DRIVER_FAILURE" for err in resp_stat.errors)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Missing calibration returns UNAVAILABLE.
# ─────────────────────────────────────────────────────────────────────────────

def test_5_missing_calibration_returns_unavailable():
    service = DeviceService(providers=[MockRealProvider()])
    engine = GatewayEngine(device_service=service)

    resp = engine.execute_tool("device.calibration.get", {"device_id": "lab-sensor-offline"})
    assert resp.state == ToolState.UNAVAILABLE
    assert resp.payload["status"] == "UNAVAILABLE"
    assert resp.payload["reason"] == "NO_CALIBRATION_RECORD"

    # Present calibration returns COMPLETED
    resp_ok = engine.execute_tool("device.calibration.get", {"device_id": "lab-sensor-01"})
    assert resp_ok.state == ToolState.COMPLETED
    assert resp_ok.payload["status"] == "AVAILABLE"
    assert "dark_counts" in resp_ok.payload["calibration_data"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Device capabilities come from actual provider state.
# ─────────────────────────────────────────────────────────────────────────────

def test_6_device_capabilities_from_actual_provider():
    service = DeviceService(providers=[MockRealProvider()])
    engine = GatewayEngine(device_service=service)

    resp = engine.execute_tool("device.describe", {"device_id": "lab-sensor-01"})
    assert resp.state == ToolState.COMPLETED
    assert resp.payload["capabilities"] == ["spectroscopy", "uv_vis", "dark_correction"]
    assert resp.payload["manufacturer"] == "Ocean Optics"
    assert resp.payload["model"] == "HR4000"
    assert resp.payload["native_units"]["SPECTRAL_INTENSITY"] == "counts"


# ─────────────────────────────────────────────────────────────────────────────
# 7. No read-only endpoint can mutate hardware.
# ─────────────────────────────────────────────────────────────────────────────

def test_7_no_read_only_endpoint_can_mutate_hardware():
    service = DeviceService(providers=[MockRealProvider()])
    engine = GatewayEngine(device_service=service)

    forbidden_calls = [
        ("actuator.move", {"axis": "x", "distance_mm": 10}),
        ("instrument.configure", {"exposure_time_ms": 100}),
        ("device.voltage.set", {"voltage_v": 5.0}),
        ("sensor.start_capture", {"duration_s": 60}),
        ("microscope.autofocus", {}),
    ]

    for tool_name, args in forbidden_calls:
        resp = engine.execute_tool(tool_name, args)
        assert resp.state == ToolState.REJECTED
        assert any(err.code == "TOOL_FORBIDDEN_PHASE1" for err in resp.errors)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Invalid device IDs are rejected.
# ─────────────────────────────────────────────────────────────────────────────

def test_8_invalid_device_ids_rejected():
    service = DeviceService(providers=[MockRealProvider()])
    engine = GatewayEngine(device_service=service)

    malicious_inputs = [
        "",
        "   ",
        "../../etc/passwd",
        "/dev/null",
        "device; rm -rf /",
        "device && echo pwned",
        "device|cat",
        "a" * 150,  # exceeds 128 chars
    ]

    for bad_id in malicious_inputs:
        resp = engine.execute_tool("device.describe", {"device_id": bad_id})
        assert resp.state == ToolState.FAILED
        assert any(err.code in ("INVALID_ARGUMENT", "MISSING_ARGUMENT") for err in resp.errors)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Tool responses match the schema.
# ─────────────────────────────────────────────────────────────────────────────

def test_9_tool_response_matches_schema():
    service = DeviceService(providers=[MockRealProvider()])
    engine = GatewayEngine(device_service=service)

    resp = engine.execute_tool("device.list")
    data = resp.model_dump()

    # Schema contract verification
    assert data["schema_version"] == "vlab.tool.v1"
    assert "request_id" in data and len(data["request_id"]) > 0
    assert "correlation_id" in data and len(data["correlation_id"]) > 0
    assert data["tool"] == "device.list"
    assert data["state"] == "COMPLETED"
    assert "created_at_utc" in data
    assert "completed_at_utc" in data
    assert isinstance(data["evidence"], list)
    assert isinstance(data["payload"], dict)
    assert isinstance(data["errors"], list)


# ─────────────────────────────────────────────────────────────────────────────
# 10. No mock fallback executes in production paths.
# ─────────────────────────────────────────────────────────────────────────────

def test_10_no_mock_fallback_in_production_paths():
    """
    Test real production SensorNodeProvider with empty live registry.
    Verifies that when no physical phone is attached, it strictly returns []
    rather than falling back to simulated or hard-coded devices.
    """
    empty_registry = ConnectionRegistry()
    provider = SensorNodeProvider(registry=empty_registry)
    
    # We do not mock adb or socket registry here:
    # If adb happens to be installed on the machine and has no devices, it returns []
    # If no devices are attached, it returns []
    devices = provider.list_devices()
    assert isinstance(devices, list)
    for dev in devices:
        # If any device is found, it must be a real ADB attached hardware, not a mock
        assert "sensornode-adb-" in dev["device_id"] or dev["device_id"] in empty_registry.devices


# ─────────────────────────────────────────────────────────────────────────────
# 11. MCP Adapter verification.
# ─────────────────────────────────────────────────────────────────────────────

def test_11_mcp_adapter_integration():
    service = DeviceService(providers=[MockRealProvider()])
    engine = GatewayEngine(device_service=service)
    adapter = MCPAdapter(engine)

    # Tool declarations
    defs = adapter.get_tool_definitions()
    names = [d["name"] for d in defs]
    assert "device_list" in names
    assert "device_describe" in names
    assert "device_status" in names
    assert "device_calibration_get" in names

    # Call device_list
    mcp_resp = adapter.call_tool("device_list", {})
    assert not mcp_resp["isError"]
    parsed = json.loads(mcp_resp["content"][0]["text"])
    assert parsed["schema_version"] == "vlab.tool.v1"
    assert len(parsed["payload"]["devices"]) == 2

    # Call unknown MCP tool
    err_resp = adapter.call_tool("actuator_move", {"axis": "x"})
    assert err_resp["isError"]
    parsed_err = json.loads(err_resp["content"][0]["text"])
    assert parsed_err["errors"][0]["code"] == "UNKNOWN_MCP_TOOL"
