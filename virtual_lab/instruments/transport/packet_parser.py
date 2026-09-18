import json
import time
import struct
from typing import Dict, Tuple

from virtual_lab.instruments.measurements import Measurement, ScientificState
from virtual_lab.instruments.camera import CameraFrame
from virtual_lab.instruments.transport.protocol_v1 import (
    MeasurementPacket,
    CameraFrameMetadata
)

class PacketDecoder:
    def __init__(self):
        self.total_received = 0
        self.total_decoded = 0
        self.total_rejected = 0
        self.last_error = None

    def decode(self, raw_json: str, active_session_id: str) -> Measurement:
        self.total_received += 1
        received_monotonic_ns = time.monotonic_ns()
        received_utc_ns = time.time_ns()
        
        try:
            packet = MeasurementPacket.model_validate_json(raw_json)
            
            m = Measurement(
                measurement_id=f"M-{received_monotonic_ns}-{packet.sequence}",
                session_id=active_session_id,
                source_session_id=packet.source_session_id,
                instrument_id=packet.device_id,
                sensor_id=packet.sensor_id,
                sequence=packet.sequence,
                device_timestamp_ns=packet.device_timestamp_ns,
                received_monotonic_ns=received_monotonic_ns,
                received_utc_ns=received_utc_ns,
                quantity=packet.measurement_type,
                values=packet.values,
                units=packet.units,
                sensor_accuracy=int(packet.accuracy) if packet.accuracy is not None and str(packet.accuracy).isdigit() else None,
                calibration_id=None,
                scientific_state=ScientificState.MEASURED
            )
            
            self.total_decoded += 1
            self.last_error = None
            return m
            
        except Exception as e:
            self.total_rejected += 1
            self.last_error = str(e)
            raise ValueError(f"Failed to parse measurement packet: {e}")

class CameraFrameDecoder:
    def __init__(self):
        self.total_received = 0
        self.total_decoded = 0
        self.total_rejected = 0
        self.last_error = None

    def decode(self, raw_bytes: bytes) -> CameraFrame:
        self.total_received += 1
        
        if len(raw_bytes) > 15 * 1024 * 1024:
            self.total_rejected += 1
            self.last_error = "Frame exceeds 15MB max size"
            raise ValueError(self.last_error)
            
        if len(raw_bytes) < 4:
            self.total_rejected += 1
            self.last_error = "Frame truncated (missing length header)"
            raise ValueError(self.last_error)
            
        meta_len = struct.unpack(">I", raw_bytes[:4])[0]
        
        if len(raw_bytes) < 4 + meta_len:
            self.total_rejected += 1
            self.last_error = f"Frame truncated (expected {4 + meta_len} bytes, got {len(raw_bytes)})"
            raise ValueError(self.last_error)
            
        try:
            meta_json = raw_bytes[4:4+meta_len].decode('utf-8')
            metadata = CameraFrameMetadata.model_validate_json(meta_json)
        except Exception as e:
            self.total_rejected += 1
            self.last_error = f"Invalid metadata JSON: {e}"
            raise ValueError(self.last_error)
            
        jpeg_bytes = raw_bytes[4+meta_len:]
        if not jpeg_bytes:
            self.total_rejected += 1
            self.last_error = "Empty JPEG payload"
            raise ValueError(self.last_error)
            
        frame = CameraFrame(
            schema_version=metadata.schema_version,
            message_type=metadata.message_type,
            device_id=metadata.device_id,
            camera_id=metadata.camera_stream_key.camera_id,
            logical_camera_id=metadata.camera_stream_key.logical_camera_id,
            physical_camera_id=metadata.camera_stream_key.physical_camera_id,
            frame_sequence=metadata.frame_sequence,
            device_timestamp_ns=metadata.device_timestamp_ns,
            received_monotonic_ns=time.monotonic_ns(),
            received_utc_ns=time.time_ns(),
            width=metadata.width,
            height=metadata.height,
            encoding=metadata.encoding,
            orientation=metadata.orientation,
            lens_facing=metadata.lens_facing,
            focal_length_mm=metadata.focal_length_mm,
            exposure_time_ns=metadata.exposure_time_ns,
            sensor_sensitivity_iso=metadata.sensor_sensitivity_iso,
            focus_distance=metadata.focus_distance_diopters,
            jpeg_bytes=jpeg_bytes,
            scientific_state=metadata.scientific_state,
            acquisition_type=metadata.acquisition_type,
            representation=metadata.representation,
            request_id=metadata.request_id
        )
        
        self.total_decoded += 1
        self.last_error = None
        
        return frame
