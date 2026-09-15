from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from virtual_lab.instruments.camera import CameraStreamKey

class ControlStateStatus(Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"

@dataclass
class CameraCapabilities:
    camera_stream_key: CameraStreamKey
    manual_focus_supported: bool = False
    minimum_focus_distance: float = 0.0 # diopters
    af_modes: List[str] = field(default_factory=list)
    
    manual_sensor_supported: bool = False
    exposure_time_range: tuple[int, int] = (0, 0) # ns
    iso_range: tuple[int, int] = (0, 0)
    frame_duration_range: tuple[int, int] = (0, 0)
    
    ae_modes: List[str] = field(default_factory=list)
    ae_compensation_range: tuple[int, int] = (0, 0)
    ae_compensation_step: float = 0.0
    
    awb_modes: List[str] = field(default_factory=list)
    awb_lock_supported: bool = False
    
    fps_ranges: List[tuple[int, int]] = field(default_factory=list)
    resolutions: List[tuple[int, int]] = field(default_factory=list)
    
    zoom_ratio_range: tuple[float, float] = (1.0, 1.0)
    
    stabilization_modes: List[str] = field(default_factory=list)
    torch_supported: bool = False
    raw_capability: bool = False

@dataclass
class ControlState:
    request_id: str
    control_type: str
    requested_value: Any
    applied_value: Any = None
    status: ControlStateStatus = ControlStateStatus.QUEUED
    error_message: Optional[str] = None
    requested_utc: int = 0
    confirmed_utc: Optional[int] = None

@dataclass
class ControlPreset:
    preset_id: str
    preset_name: str
    camera_stream_key: CameraStreamKey
    requested_configuration: Dict[str, Any]
    
