import json
import time
from typing import Dict, Tuple

from virtual_lab.instruments.measurements import Measurement, ScientificState

StreamKey = Tuple[str, str, str] # instrument_id, sensor_id, measurement_type

EXPECTED_FIELDS = {
    "MAGNETIC_FIELD": {
        "bx": "uT",
        "by": "uT",
        "bz": "uT",
    },
    "ACCELERATION": {
        "ax": "m/s^2",
        "ay": "m/s^2",
        "az": "m/s^2",
    },
    "ANGULAR_VELOCITY": {
        "wx": "rad/s",
        "wy": "rad/s",
        "wz": "rad/s",
    },
    "ILLUMINANCE": {
        "illuminance": "lx",
    },
    "PRESSURE": {
        "pressure": "hPa",
    },
}

class PacketDecoder:
    def __init__(self):
        self.seq_counters: Dict[StreamKey, int] = {}
        
        # Diagnostics
        self.total_received = 0
        self.total_decoded = 0
        self.total_rejected = 0
        self.last_measurement_type = None
        self.last_sensor_id = None
        self.last_sequence = None
        self.last_error = None

    def decode(self, raw_json: str, active_session_id: str) -> Measurement:
        self.total_received += 1
        received_monotonic_ns = time.monotonic_ns()
        received_utc_ns = time.time_ns()
        
        try:
            packet = json.loads(raw_json)
            
            instrument_id = packet.get("device_id", "ANDROID-UNKNOWN")
            source_session_id = packet.get("session_id", packet.get("source_session_id"))
            
            # Determine measurement type and sensor id
            measurement_type = packet.get("measurement_type")
            sensor_id = packet.get("sensor_id", packet.get("sensor", {}).get("name", "unknown"))
            
            if not measurement_type:
                # Legacy fallback
                if "x_ut" in packet.get("values", {}):
                    measurement_type = "MAGNETIC_FIELD"
                    sensor_id = "magnetometer"
                else:
                    raise ValueError("Missing measurement_type and not a recognized legacy packet")
                    
            if measurement_type not in EXPECTED_FIELDS:
                raise ValueError(f"Unsupported measurement_type: {measurement_type}")
                
            expected_contract = EXPECTED_FIELDS[measurement_type]
            
            values = packet.get("values")
            if not values:
                raise ValueError("Missing 'values' in packet")
                
            is_legacy = False
            # Handle legacy magnetometer mapping
            if measurement_type == "MAGNETIC_FIELD" and "x_ut" in values:
                values = {
                    "bx": values.get("x_ut", 0.0),
                    "by": values.get("y_ut", 0.0),
                    "bz": values.get("z_ut", 0.0)
                }
                is_legacy = True
                
            units = packet.get("units")
            if not units:
                if is_legacy:
                    units = {"bx": "uT", "by": "uT", "bz": "uT"}
                else:
                    raise ValueError("Missing 'units' in packet and not a legacy packet")
                    
            # Validate contract
            for key, expected_unit in expected_contract.items():
                if key not in values:
                    raise ValueError(f"Missing required value key: {key}")
                if key not in units:
                    raise ValueError(f"Missing required unit for key: {key}")
                if units[key] != expected_unit:
                    raise ValueError(f"Unit mismatch for {key}: expected {expected_unit}, got {units[key]}")
            
            # Sequence
            seq = packet.get("sequence")
            key = (instrument_id, sensor_id, measurement_type)
            if seq is None:
                self.seq_counters[key] = self.seq_counters.get(key, 0) + 1
                seq = self.seq_counters[key]
            else:
                self.seq_counters[key] = seq
                
            device_ts_ns = packet.get("timestamp_monotonic_ns", packet.get("device_timestamp_ns", 0))
            
            sensor_meta = packet.get("sensor", {})
            accuracy = sensor_meta.get("accuracy", packet.get("accuracy"))
            
            m = Measurement(
                measurement_id=f"M-{received_monotonic_ns}-{seq}",
                session_id=active_session_id,
                source_session_id=source_session_id,
                instrument_id=instrument_id,
                sensor_id=sensor_id,
                sequence=seq,
                device_timestamp_ns=device_ts_ns,
                received_monotonic_ns=received_monotonic_ns,
                received_utc_ns=received_utc_ns,
                quantity=measurement_type,
                values=values,
                units=units,
                sensor_accuracy=accuracy,
                calibration_id=None,
                scientific_state=ScientificState.MEASURED
            )
            
            self.total_decoded += 1
            self.last_measurement_type = measurement_type
            self.last_sensor_id = sensor_id
            self.last_sequence = seq
            self.last_error = None
            return m
            
        except Exception as e:
            self.total_rejected += 1
            self.last_error = str(e)
            raise ValueError(f"Failed to parse measurement packet: {e}")

import struct

class CameraFrameDecoder:
    def __init__(self):
        self.total_received = 0
        self.total_decoded = 0
        self.total_rejected = 0
        self.last_error = None
        self.last_message_type = None

    def decode(self, raw_bytes: bytes) -> dict:
        self.total_received += 1
        
        # Enforce max frame size, e.g., 10MB
        if len(raw_bytes) > 10 * 1024 * 1024:
            self.total_rejected += 1
            self.last_error = "Frame exceeds 10MB max size"
            raise ValueError(self.last_error)
            
        if len(raw_bytes) < 4:
            self.total_rejected += 1
            self.last_error = "Frame truncated (missing length header)"
            raise ValueError(self.last_error)
            
        # Parse 4-byte length (big-endian unsigned 32-bit integer)
        meta_len = struct.unpack(">I", raw_bytes[:4])[0]
        
        if len(raw_bytes) < 4 + meta_len:
            self.total_rejected += 1
            self.last_error = f"Frame truncated (expected {4 + meta_len} bytes, got {len(raw_bytes)})"
            raise ValueError(self.last_error)
            
        try:
            meta_json = raw_bytes[4:4+meta_len].decode('utf-8')
            metadata = json.loads(meta_json)
        except Exception as e:
            self.total_rejected += 1
            self.last_error = f"Invalid metadata JSON: {e}"
            raise ValueError(self.last_error)
            
        jpeg_bytes = raw_bytes[4+meta_len:]
        if not jpeg_bytes:
            self.total_rejected += 1
            self.last_error = "Empty JPEG payload"
            raise ValueError(self.last_error)
            
        schema_version = metadata.get("schema_version")
        if schema_version != "1":
            self.total_rejected += 1
            self.last_error = f"Unsupported schema_version: {schema_version}"
            raise ValueError(self.last_error)
            
        msg_type = metadata.get("message_type")
        if msg_type not in ["CAMERA_PREVIEW_FRAME", "CAMERA_SCIENTIFIC_FRAME"]:
            self.total_rejected += 1
            self.last_error = f"Unsupported message_type: {msg_type}"
            raise ValueError(self.last_error)
            
        device_id = metadata.get("device_id")
        camera_id = metadata.get("camera_id")
        if not device_id or not camera_id:
            self.total_rejected += 1
            self.last_error = "Missing required IDs (device_id, camera_id)"
            raise ValueError(self.last_error)
            
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)
        if width <= 0 or height <= 0:
            self.total_rejected += 1
            self.last_error = f"Invalid resolution: {width}x{height}"
            raise ValueError(self.last_error)
            
        encoding = metadata.get("encoding", "JPEG")
        if encoding != "JPEG":
            self.total_rejected += 1
            self.last_error = f"Unsupported encoding: {encoding}"
            raise ValueError(self.last_error)
            
        from virtual_lab.instruments.camera import CameraFrame
        frame = CameraFrame(
            schema_version=schema_version,
            message_type=msg_type,
            device_id=device_id,
            camera_id=camera_id,
            logical_camera_id=metadata.get("logical_camera_id"),
            physical_camera_id=metadata.get("physical_camera_id"),
            frame_sequence=metadata.get("frame_sequence", 0),
            device_timestamp_ns=metadata.get("device_timestamp_ns", 0),
            received_monotonic_ns=time.monotonic_ns(),
            received_utc_ns=time.time_ns(),
            width=width,
            height=height,
            encoding=encoding,
            orientation=metadata.get("orientation", 0),
            lens_facing=metadata.get("lens_facing", "UNKNOWN"),
            focal_length_mm=metadata.get("focal_length_mm"),
            exposure_time_ns=metadata.get("exposure_time_ns"),
            sensor_sensitivity_iso=metadata.get("sensor_sensitivity_iso"),
            focus_distance=metadata.get("focus_distance"),
            jpeg_bytes=jpeg_bytes,
            scientific_state=metadata.get("scientific_state", "MEASURED"),
            acquisition_type=metadata.get("acquisition_type", "CAMERA_FRAME"),
            representation=metadata.get("representation", "ISP_PROCESSED"),
            request_id=metadata.get("request_id")
        )
        
        self.total_decoded += 1
        self.last_message_type = msg_type
        self.last_error = None
        
        return frame
