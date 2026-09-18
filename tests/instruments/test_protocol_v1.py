import pytest
import json
import os
from virtual_lab.instruments.transport.protocol_v1 import (
    ChannelHello, InstrumentDescriptor, MeasurementPacket, ErrorEnvelope,
    CameraFrameMetadata, CameraControlRequest, CameraControlResult,
    CameraCapabilities, CameraState, ScientificCaptureRequest, ScientificCaptureResult,
    ScientificFrameAck
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "protocol_v1")

def load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURES_DIR, f"{name}.json"), "r") as f:
        return json.load(f)

def test_channel_hello():
    data = load_fixture("channel_hello")
    model = ChannelHello.model_validate(data)
    assert model.message_type == "CHANNEL_HELLO"
    assert model.device_id == "DEV-123"

def test_instrument_descriptor():
    data = load_fixture("instrument_descriptor")
    model = InstrumentDescriptor.model_validate(data)
    assert model.message_type == "INSTRUMENT_DESCRIPTOR"
    assert "Core" in model.protocol_profiles

def test_measurement_packet():
    data = load_fixture("measurement_packet")
    model = MeasurementPacket.model_validate(data)
    assert model.message_type == "MEASUREMENT_PACKET"
    assert model.measurement_type == "MAGNETIC_FIELD"
    assert model.units["bx"] == "uT"

def test_error_envelope():
    data = load_fixture("error_envelope")
    model = ErrorEnvelope.model_validate(data)
    assert model.severity == "ERROR"
    assert model.error_code == "E123"

def test_camera_frame_metadata():
    data = load_fixture("camera_frame_metadata")
    model = CameraFrameMetadata.model_validate(data)
    assert model.message_type == "CAMERA_PREVIEW_FRAME"
    assert model.payload_size_bytes == 102400

def test_camera_control_request():
    data = load_fixture("camera_control_request")
    model = CameraControlRequest.model_validate(data)
    assert model.control_type == "GET_CAPABILITIES"

def test_camera_control_result():
    data = load_fixture("camera_control_result")
    model = CameraControlResult.model_validate(data)
    assert model.overall_status == "APPLIED"
    assert "exposure_time_ns" in model.parameter_results
    assert model.parameter_results["exposure_time_ns"].status == "APPLIED"

def test_camera_capabilities():
    data = load_fixture("camera_capabilities")
    model = CameraCapabilities.model_validate(data)
    assert model.camera_stream_key.camera_id == "0"

def test_camera_state():
    data = load_fixture("camera_state")
    model = CameraState.model_validate(data)
    assert model.device_id == "DEV-123"

def test_scientific_capture_request():
    data = load_fixture("scientific_capture_request")
    model = ScientificCaptureRequest.model_validate(data)
    assert model.request_id == "REQ-2"

def test_scientific_capture_result():
    data = load_fixture("scientific_capture_result")
    model = ScientificCaptureResult.model_validate(data)
    assert model.status == "COMPLETED"

def test_scientific_frame_ack():
    data = load_fixture("scientific_frame_ack")
    model = ScientificFrameAck.model_validate(data)
    assert model.status == "COMMITTED"
    assert model.artifact_sha256 == "abcdef123456"
