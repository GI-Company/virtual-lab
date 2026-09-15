import time
import hashlib
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from virtual_lab.instruments.camera import CameraStreamKey

@dataclass
class SpatialCalibration:
    calibration_id: str
    device_id: str
    camera_stream_key: CameraStreamKey
    optical_setup_id: str
    source_frame_hash: str
    
    resolution_width: int
    resolution_height: int
    orientation: int
    
    reference_distance: float
    reference_unit: str
    reference_distance_um: float
    
    pixel_line_start: tuple[float, float]
    pixel_line_end: tuple[float, float]
    pixel_distance: float
    
    microns_per_pixel_x: float
    microns_per_pixel_y: float
    
    isotropic_scale_assumed: bool
    calibration_method: str
    
    created_utc: int
    operator: str
    notes: str = ""

@dataclass
class OpticalSetup:
    setup_id: str
    device_id: str
    camera_stream_key: CameraStreamKey
    external_lens: Optional[str] = None
    objective: Optional[str] = None
    illumination: Optional[str] = None
    resolution: Optional[str] = None
    orientation: Optional[int] = None
    zoom_crop_configuration: Optional[str] = None
    spatial_calibration_id: Optional[str] = None
    notes: str = ""

@dataclass
class RegionOfInterest:
    roi_id: str
    source_frame_hash: str
    optical_setup_id: str
    spatial_calibration_id: Optional[str]
    roi_type: str  # e.g., "RECTANGLE", "LINE", "POLYGON"
    source_pixel_coordinates: List[tuple[float, float]]
    analysis_operations: List[str]
    analysis_parameters: Dict[str, Any]
    analysis_results: Dict[str, Any]
    scientific_state: str = "DERIVED"

@dataclass
class AnalysisRun:
    analysis_run_id: str
    source_frame_hash: str
    roi_ids: List[str]
    algorithm: str
    algorithm_version: str
    parameters: Dict[str, Any]
    results: Dict[str, Any]
    created_utc: int

import uuid

def generate_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"

def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
