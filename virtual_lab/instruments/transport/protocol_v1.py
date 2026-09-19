from typing import Dict, List, Optional, Union, Literal, Tuple
from pydantic import BaseModel, Field

# Core Protocol Models

class ChannelHello(BaseModel):
    message_type: Literal["CHANNEL_HELLO"] = "CHANNEL_HELLO"
    schema_version: str = "1"
    device_id: str
    channel: Literal["sensors", "camera", "control"]

class InstrumentDescriptor(BaseModel):
    message_type: Literal["INSTRUMENT_DESCRIPTOR"] = "INSTRUMENT_DESCRIPTOR"
    schema_version: str = "1"
    device_id: str
    instrument_type: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    software_version: Optional[str] = None
    protocol_profiles: List[str]
    capabilities: List[str]

class MeasurementPacket(BaseModel):
    message_type: Literal["MEASUREMENT_PACKET"] = "MEASUREMENT_PACKET"
    schema_version: str = "1"
    device_id: str
    stream_id: str
    source_session_id: Optional[str] = None
    measurement_type: str
    sensor_id: str
    sequence: int
    device_timestamp_ns: int
    device_timebase: Literal["MONOTONIC"]
    device_utc_ns: Optional[int] = None
    values: Dict[str, float]
    units: Dict[str, str]
    accuracy: Optional[Union[int, str]] = None

class ErrorEnvelope(BaseModel):
    message_type: Literal["ERROR_ENVELOPE"] = "ERROR_ENVELOPE"
    schema_version: str = "1"
    device_id: str
    severity: Literal["WARNING", "ERROR", "FATAL"]
    error_code: str
    message: str
    details: Dict[str, str] = Field(default_factory=dict)

# Camera Profile Models

class CameraStreamKey(BaseModel):
    camera_id: str
    logical_camera_id: Optional[str] = None
    physical_camera_id: Optional[str] = None

class CameraFrameMetadata(BaseModel):
    message_type: Literal["CAMERA_PREVIEW_FRAME", "CAMERA_SCIENTIFIC_FRAME"] = "CAMERA_PREVIEW_FRAME"
    schema_version: Literal["1"] = "1"
    device_id: str
    stream_id: str
    camera_stream_key: CameraStreamKey
    frame_sequence: int
    device_timestamp_ns: int
    device_timebase: Literal["MONOTONIC"]
    device_utc_ns: Optional[int] = None
    width: int
    height: int
    encoding: Literal["JPEG", "RAW"]
    orientation: int
    lens_facing: Literal["FRONT", "BACK", "EXTERNAL"]
    focal_length_mm: float
    exposure_time_ns: Optional[int] = None
    sensor_sensitivity_iso: Optional[int] = None
    focus_distance_diopters: Optional[float] = None
    scientific_state: str = "MEASURED"
    acquisition_type: str = "CAMERA_FRAME"
    representation: Literal["ISP_PROCESSED", "SENSOR_RAW"]
    request_id: Optional[str] = None
    payload_size_bytes: int
    payload_sha256: Optional[str] = None

    from pydantic import model_validator
    @model_validator(mode='after')
    def check_resolution(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Invalid resolution: {self.width}x{self.height}")
        return self

class CameraControlRequest(BaseModel):
    message_type: Literal["CAMERA_CONTROL_REQUEST"] = "CAMERA_CONTROL_REQUEST"
    schema_version: str = "1"
    request_id: str
    device_id: str
    camera_stream_key: Optional[CameraStreamKey] = None
    control_type: Literal[
        "SET_PARAMETERS", "GET_CAPABILITIES", "GET_STATE",
        "GET_CAMERA_INVENTORY", "SELECT_CAMERA",
        "START_CAMERA_STREAM", "STOP_CAMERA_STREAM"
    ]
    requested_parameters: Optional[Dict[str, Optional[Union[int, float, str]]]] = None

class ParameterResult(BaseModel):
    requested: Optional[Union[int, float, str]]
    applied: Optional[Union[int, float, str]] = None
    status: Literal["APPLIED", "PARTIALLY_APPLIED", "UNCONFIRMED", "REJECTED", "FAILED"]

class CameraControlResult(BaseModel):
    message_type: Literal["CAMERA_CONTROL_RESULT"] = "CAMERA_CONTROL_RESULT"
    schema_version: str = "1"
    request_id: str
    device_id: str
    overall_status: Literal["APPLIED", "PARTIALLY_APPLIED", "UNCONFIRMED", "REJECTED", "FAILED"]
    parameter_results: Optional[Dict[str, ParameterResult]] = None
    error_message: Optional[str] = None

class CameraCapabilities(BaseModel):
    message_type: Literal["CAMERA_CAPABILITIES"] = "CAMERA_CAPABILITIES"
    schema_version: str = "1"
    device_id: str
    camera_stream_key: CameraStreamKey
    manual_sensor_supported: Optional[bool] = None
    manual_focus_supported: Optional[bool] = None
    exposure_time_range_ns: Optional[Tuple[int, int]] = None
    iso_range: Optional[Tuple[int, int]] = None
    minimum_focus_distance_diopters: Optional[float] = None
    af_modes: List[str] = Field(default_factory=list)
    ae_modes: List[str] = Field(default_factory=list)
    ae_compensation_range: Optional[Tuple[int, int]] = None
    ae_compensation_step: Optional[float] = None
    awb_modes: List[str] = Field(default_factory=list)
    awb_lock_supported: Optional[bool] = None
    fps_ranges: List[Tuple[int, int]] = Field(default_factory=list)
    resolutions: List[Tuple[int, int]] = Field(default_factory=list)
    zoom_ratio_range: Optional[Tuple[float, float]] = None
    stabilization_modes: List[str] = Field(default_factory=list)
    torch_supported: Optional[bool] = None
    raw_capability: Optional[bool] = None

class CameraState(BaseModel):
    message_type: Literal["CAMERA_STATE"] = "CAMERA_STATE"
    schema_version: str = "1"
    device_id: str
    camera_stream_key: CameraStreamKey
    current_exposure_time_ns: Optional[int] = None
    current_iso: Optional[int] = None
    current_focus_distance_diopters: Optional[float] = None
    current_af_mode: Optional[str] = None
    thermal_status: Optional[str] = None

class ScientificCaptureRequest(BaseModel):
    message_type: Literal["SCIENTIFIC_CAPTURE_REQUEST"] = "SCIENTIFIC_CAPTURE_REQUEST"
    schema_version: str = "1"
    request_id: str
    device_id: str
    camera_stream_key: CameraStreamKey
    parameters: Dict[str, Optional[Union[int, float, str]]] = Field(default_factory=dict)

class ScientificCaptureResult(BaseModel):
    message_type: Literal["SCIENTIFIC_CAPTURE_RESULT"] = "SCIENTIFIC_CAPTURE_RESULT"
    schema_version: str = "1"
    request_id: str
    device_id: str
    status: Literal["COMPLETED", "FAILED"]
    device_timestamp_ns: int
    error_message: Optional[str] = None

class ScientificFrameAck(BaseModel):
    message_type: Literal["SCIENTIFIC_FRAME_ACK"] = "SCIENTIFIC_FRAME_ACK"
    schema_version: str = "1"
    request_id: str
    device_id: str
    status: Literal["COMMITTED", "REJECTED"]
    artifact_sha256: Optional[str] = None
    error_message: Optional[str] = None
