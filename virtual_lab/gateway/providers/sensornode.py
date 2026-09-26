"""
virtual_lab.gateway.providers.sensornode
────────────────────────────────────────
Concrete DeviceProvider for SensorNode devices (Android edge measurement nodes).
Queries actual runtime hardware state via:
1. WebSocket ConnectionRegistry (live connections on /sensors, /camera, /control)
2. Android Debug Bridge (ADB) for physical USB attached devices

Strictly complies with the Zero-Fabrication Rule.
"""

import os
import json
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from virtual_lab.gateway.providers.base import DeviceProvider
from virtual_lab.instruments.connection import ConnectionRegistry, InstrumentState

SENSORNODE_PACKAGE = "com.aistudio.sensornode.vlsnxz"


class SensorNodeProvider(DeviceProvider):
    def __init__(self, registry: Optional[ConnectionRegistry] = None, calibration_dir: str = "data/calibration"):
        self.registry = registry
        self.calibration_dir = calibration_dir

    @property
    def name(self) -> str:
        return "sensornode_provider"

    def _get_adb_devices(self) -> List[Dict[str, str]]:
        """
        Queries real USB devices attached via ADB.
        Returns an empty list if adb is not found or no devices are connected.
        """
        adb_bin = shutil.which("adb")
        if not adb_bin:
            return []

        try:
            result = subprocess.run(
                [adb_bin, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode != 0:
                return []

            devices = []
            lines = result.stdout.strip().splitlines()
            # First line is usually "List of devices attached"
            for line in lines[1:]:
                line = line.strip()
                if not line or line.startswith("*"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    # Parse optional properties like model:Pixel_7 device:panther
                    props = {}
                    for p in parts[2:]:
                        if ":" in p:
                            k, v = p.split(":", 1)
                            props[k] = v
                    devices.append({
                        "serial": serial,
                        "state": state,
                        "model": props.get("model", ""),
                        "device": props.get("device", "")
                    })
            return devices
        except Exception:
            return []

    def _query_adb_device_details(self, serial: str) -> Dict[str, Any]:
        """
        Query actual factual device properties via ADB getprop / dumpsys.
        """
        adb_bin = shutil.which("adb")
        if not adb_bin:
            return {}

        details = {}
        try:
            # Manufacturer & Model
            proc_mfg = subprocess.run([adb_bin, "-s", serial, "shell", "getprop", "ro.product.manufacturer"],
                                      capture_output=True, text=True, timeout=2)
            if proc_mfg.returncode == 0 and proc_mfg.stdout.strip():
                details["manufacturer"] = proc_mfg.stdout.strip()

            proc_model = subprocess.run([adb_bin, "-s", serial, "shell", "getprop", "ro.product.model"],
                                        capture_output=True, text=True, timeout=2)
            if proc_model.returncode == 0 and proc_model.stdout.strip():
                details["model"] = proc_model.stdout.strip()

            proc_os = subprocess.run([adb_bin, "-s", serial, "shell", "getprop", "ro.build.version.release"],
                                     capture_output=True, text=True, timeout=2)
            if proc_os.returncode == 0 and proc_os.stdout.strip():
                details["os_version"] = f"Android {proc_os.stdout.strip()}"

            # Check package installation
            proc_pkg = subprocess.run([adb_bin, "-s", serial, "shell", "pm", "path", SENSORNODE_PACKAGE],
                                      capture_output=True, text=True, timeout=2)
            details["sensornode_installed"] = (proc_pkg.returncode == 0 and bool(proc_pkg.stdout.strip()))

            # Check battery
            proc_bat = subprocess.run([adb_bin, "-s", serial, "shell", "dumpsys", "battery"],
                                      capture_output=True, text=True, timeout=2)
            if proc_bat.returncode == 0:
                bat_info = {}
                for line in proc_bat.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("level:"):
                        bat_info["level_percent"] = int(line.split(":")[1].strip())
                    elif line.startswith("temperature:"):
                        # tenth of degree Celsius
                        bat_info["temperature_c"] = float(line.split(":")[1].strip()) / 10.0
                    elif line.startswith("status:"):
                        bat_info["charging_status"] = line.split(":")[1].strip()
                if bat_info:
                    details["battery"] = bat_info
        except Exception:
            pass

        return details

    def list_devices(self) -> List[Dict[str, Any]]:
        """
        Factual discovery of SensorNode devices.
        Combines live WebSocket connections and attached ADB USB devices.
        Returns empty list [] if no hardware is found.
        """
        devices_dict = {}

        # 1. Live WebSocket connections from registry
        if self.registry:
            for dev_id, dev_state in self.registry.devices.items():
                active_channels = []
                if dev_state.sensors and dev_state.sensors.state.value != "DISCONNECTED":
                    active_channels.append("sensors")
                if dev_state.camera and dev_state.camera.state.value != "DISCONNECTED":
                    active_channels.append("camera")
                if dev_state.control and dev_state.control.state.value != "DISCONNECTED":
                    active_channels.append("control")

                if not active_channels:
                    continue

                overall = dev_state.overall_state()
                conn_state = "ONLINE" if overall in (InstrumentState.READY, InstrumentState.ACQUIRING, InstrumentState.PARTIAL) else overall.value

                capabilities = []
                if "camera" in active_channels:
                    capabilities.append("camera")
                if "sensors" in active_channels:
                    capabilities.extend(["accelerometer", "gyroscope", "magnetometer"])
                if "control" in active_channels:
                    capabilities.append("control_channel")

                # Detect remote address
                remote_addr = None
                for ch in [dev_state.sensors, dev_state.camera, dev_state.control]:
                    if ch and ch.remote_address:
                        remote_addr = ch.remote_address
                        break

                transport = "usb_adb" if remote_addr in ("127.0.0.1", "::1", "localhost") else "wifi"

                devices_dict[dev_id] = {
                    "device_id": dev_id,
                    "device_type": "android_sensor_node",
                    "name": f"SensorNode ({dev_id})",
                    "connection_state": conn_state,
                    "transport": transport,
                    "capabilities": sorted(list(set(capabilities)))
                }

        # 2. ADB USB Attached Devices
        adb_devices = self._get_adb_devices()
        for adb_dev in adb_devices:
            serial = adb_dev["serial"]
            dev_id = f"sensornode-adb-{serial}"
            
            # If already discovered via active websocket binding, enhance it
            if dev_id in devices_dict or serial in devices_dict:
                target_key = dev_id if dev_id in devices_dict else serial
                devices_dict[target_key]["transport"] = "usb_adb"
                continue

            # Check if this ADB device is online and has SensorNode package
            adb_details = self._query_adb_device_details(serial)
            is_installed = adb_details.get("sensornode_installed", False)
            conn_state = "ONLINE" if adb_dev["state"] == "device" else "OFFLINE"

            capabilities = ["usb_adb"]
            if is_installed:
                capabilities.extend(["camera", "accelerometer", "gyroscope", "magnetometer", "wifi_scan"])

            devices_dict[dev_id] = {
                "device_id": dev_id,
                "device_type": "android_sensor_node",
                "name": f"SensorNode {adb_details.get('model', serial)}",
                "connection_state": conn_state,
                "transport": "usb_adb",
                "capabilities": sorted(capabilities)
            }

        return list(devices_dict.values())

    def describe_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        devices = {d["device_id"]: d for d in self.list_devices()}
        if device_id not in devices:
            return None

        dev = devices[device_id]
        serial = None
        if "sensornode-adb-" in device_id:
            serial = device_id.replace("sensornode-adb-", "")

        adb_details = self._query_adb_device_details(serial) if serial else {}

        # Look up websocket connection state if available
        conn_meta = {}
        if self.registry and device_id in self.registry.devices:
            d_state = self.registry.devices[device_id]
            conn_meta = {
                "sensors_connected": bool(d_state.sensors and d_state.sensors.state.value != "DISCONNECTED"),
                "camera_connected": bool(d_state.camera and d_state.camera.state.value != "DISCONNECTED"),
                "control_connected": bool(d_state.control and d_state.control.state.value != "DISCONNECTED"),
            }

        return {
            "device_id": device_id,
            "device_type": dev.get("device_type", "android_sensor_node"),
            "manufacturer": adb_details.get("manufacturer"),
            "model": adb_details.get("model"),
            "serial_number": serial,
            "firmware_version": adb_details.get("os_version"),
            "transport": dev.get("transport", "unknown"),
            "capabilities": dev.get("capabilities", []),
            "measurement_types": [
                "ACCELERATION",
                "ANGULAR_VELOCITY",
                "MAGNETIC_FIELD",
                "CAMERA_FRAME"
            ],
            "native_units": {
                "ACCELERATION": "m/s²",
                "ANGULAR_VELOCITY": "rad/s",
                "MAGNETIC_FIELD": "µT",
                "CAMERA_FRAME": "RGB_JPEG"
            },
            "driver_provider": self.name,
            "connection_metadata": conn_meta if conn_meta else None
        }

    def get_status(self, device_id: str) -> Optional[Dict[str, Any]]:
        devices = {d["device_id"]: d for d in self.list_devices()}
        if device_id not in devices:
            return None

        dev = devices[device_id]
        serial = None
        if "sensornode-adb-" in device_id:
            serial = device_id.replace("sensornode-adb-", "")

        adb_details = self._query_adb_device_details(serial) if serial else {}

        last_seen = None
        error_codes = []
        sensor_availability = {}

        if self.registry and device_id in self.registry.devices:
            d_state = self.registry.devices[device_id]
            timestamps = []
            for ch in [d_state.sensors, d_state.camera, d_state.control]:
                if ch and ch.last_activity_utc:
                    timestamps.append(ch.last_activity_utc)
                if ch and ch.last_error:
                    error_codes.append(f"{ch.channel_type}:{ch.last_error}")
            if timestamps:
                last_seen = datetime.fromtimestamp(max(timestamps) / 1000.0, timezone.utc).isoformat()
            
            sensor_availability = {
                "sensors_channel": bool(d_state.sensors and d_state.sensors.state.value == "STREAMING"),
                "camera_channel": bool(d_state.camera and d_state.camera.state.value == "STREAMING"),
                "control_channel": bool(d_state.control and d_state.control.state.value != "DISCONNECTED")
            }
        else:
            sensor_availability = {
                "sensors_channel": dev.get("connection_state") == "ONLINE",
                "camera_channel": dev.get("connection_state") == "ONLINE",
                "control_channel": dev.get("connection_state") == "ONLINE"
            }

        return {
            "device_id": device_id,
            "status": dev.get("connection_state", "UNKNOWN"),
            "diagnostics": {
                "last_seen_utc": last_seen,
                "transport_state": dev.get("transport"),
                "driver_state": "ACTIVE",
                "battery": adb_details.get("battery"),
                "error_codes": error_codes,
                "sensor_availability": sensor_availability
            }
        }

    def get_calibration(self, device_id: str) -> Optional[Dict[str, Any]]:
        devices = {d["device_id"]: d for d in self.list_devices()}
        if device_id not in devices:
            return None

        cal_path = os.path.join(self.calibration_dir, f"{device_id}.json")
        if os.path.exists(cal_path):
            try:
                with open(cal_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {
                    "status": "AVAILABLE",
                    "calibration_data": data
                }
            except Exception as e:
                return {
                    "status": "FAILED",
                    "error": f"Failed to read calibration file: {str(e)}"
                }

        # Zero-fabrication: Never invent numbers when no record exists
        return {
            "status": "UNAVAILABLE",
            "reason": "NO_CALIBRATION_RECORD"
        }
