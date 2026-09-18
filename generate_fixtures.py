import json
import os
from virtual_lab.instruments.transport.protocol_v1 import (
    ChannelHello, InstrumentDescriptor, MeasurementPacket, ErrorEnvelope,
    CameraFrameMetadata, CameraStreamKey, CameraControlRequest, CameraControlResult,
    CameraCapabilities, CameraState, ScientificCaptureRequest, ScientificCaptureResult,
    ScientificFrameAck, ParameterResult
)

FIXTURES_DIR = "tests/fixtures/protocol_v1"

def save_fixture(name: str, model):
    path = os.path.join(FIXTURES_DIR, f"{name}.json")
    with open(path, "w") as f:
        f.write(model.model_dump_json(indent=2))

hello = ChannelHello(device_id="DEV-123", channel="sensors")
save_fixture("channel_hello", hello)

desc = InstrumentDescriptor(
    device_id="DEV-123", instrument_type="PhoneCamera",
    protocol_profiles=["Core", "Camera Profile v1"], capabilities=["telemetry", "camera"]
)
save_fixture("instrument_descriptor", desc)

meas = MeasurementPacket(
    device_id="DEV-123", stream_id="STR-001", measurement_type="MAGNETIC_FIELD",
    sensor_id="mag0", sequence=42, device_timestamp_ns=1000000000,
    device_timebase="MONOTONIC", values={"bx": 1.0, "by": 2.0, "bz": 3.0},
    units={"bx": "uT", "by": "uT", "bz": "uT"}
)
save_fixture("measurement_packet", meas)

err = ErrorEnvelope(
    device_id="DEV-123", severity="ERROR", error_code="E123", message="Test error"
)
save_fixture("error_envelope", err)

cam_key = CameraStreamKey(camera_id="0")

meta = CameraFrameMetadata(
    message_type="CAMERA_PREVIEW_FRAME", device_id="DEV-123", stream_id="STR-001",
    camera_stream_key=cam_key, frame_sequence=100, device_timestamp_ns=2000000000,
    device_timebase="MONOTONIC", width=1920, height=1080, encoding="JPEG",
    orientation=90, lens_facing="BACK", focal_length_mm=4.0,
    representation="ISP_PROCESSED", payload_size_bytes=102400
)
save_fixture("camera_frame_metadata", meta)

ctrl_req = CameraControlRequest(
    request_id="REQ-1", device_id="DEV-123", camera_stream_key=cam_key,
    control_type="GET_CAPABILITIES"
)
save_fixture("camera_control_request", ctrl_req)

ctrl_res = CameraControlResult(
    request_id="REQ-1", device_id="DEV-123", overall_status="APPLIED",
    parameter_results={"exposure_time_ns": ParameterResult(requested=1000, applied=1000, status="APPLIED")}
)
save_fixture("camera_control_result", ctrl_res)

caps = CameraCapabilities(
    device_id="DEV-123", camera_stream_key=cam_key
)
save_fixture("camera_capabilities", caps)

state = CameraState(
    device_id="DEV-123", camera_stream_key=cam_key
)
save_fixture("camera_state", state)

sci_req = ScientificCaptureRequest(
    request_id="REQ-2", device_id="DEV-123", camera_stream_key=cam_key
)
save_fixture("scientific_capture_request", sci_req)

sci_res = ScientificCaptureResult(
    request_id="REQ-2", device_id="DEV-123", status="COMPLETED", device_timestamp_ns=3000000000
)
save_fixture("scientific_capture_result", sci_res)

ack = ScientificFrameAck(
    request_id="REQ-2", device_id="DEV-123", status="COMMITTED", artifact_sha256="abcdef123456"
)
save_fixture("scientific_frame_ack", ack)
