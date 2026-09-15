from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class CameraStreamKey:
    device_id: str
    camera_id: str
    logical_camera_id: Optional[str]
    physical_camera_id: Optional[str]

@dataclass(frozen=True)
class CameraFrame:
    schema_version: str
    message_type: str
    
    device_id: str
    camera_id: str
    logical_camera_id: Optional[str]
    physical_camera_id: Optional[str]
    
    frame_sequence: int
    
    device_timestamp_ns: int
    received_monotonic_ns: int
    received_utc_ns: int
    
    width: int
    height: int
    encoding: str
    orientation: int
    
    lens_facing: str
    focal_length_mm: Optional[float]
    exposure_time_ns: Optional[int]
    sensor_sensitivity_iso: Optional[int]
    focus_distance: Optional[float]
    
    jpeg_bytes: bytes
    
    scientific_state: str = "MEASURED"
    acquisition_type: str = "CAMERA_FRAME"
    representation: str = "ISP_PROCESSED"
    request_id: Optional[str] = None
    
    @property
    def stream_key(self) -> CameraStreamKey:
        return CameraStreamKey(
            device_id=self.device_id,
            camera_id=self.camera_id,
            logical_camera_id=self.logical_camera_id,
            physical_camera_id=self.physical_camera_id
        )

@dataclass
class CameraStreamState:
    key: CameraStreamKey
    epoch: int = 0
    last_sequence: Optional[int] = None
    last_device_timestamp_ns: Optional[int] = None
    frames_received: int = 0
    dropped: int = 0
    duplicates: int = 0
    out_of_order: int = 0

    def calculate_rate(self) -> float:
        # We will handle observed Hz in the UI/ViewModel layer based on sliding window timestamps
        return 0.0
