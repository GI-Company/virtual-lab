import pytest
import json
import numpy as np
from virtual_lab.instruments.transport.control_parser import ControlMessageDecoder
from virtual_lab.instruments.camera import CameraStreamKey
from virtual_lab.instruments.control import ControlStateStatus
from virtual_lab.instruments.analysis import calculate_focus_metric

def test_capabilities_parsing():
    decoder = ControlMessageDecoder()
    raw = json.dumps({
        "message_type": "CAMERA_CAPABILITIES",
        "camera_stream_key": {
            "device_id": "DEV1",
            "camera_id": "0",
            "logical_camera_id": "0",
            "physical_camera_id": "2"
        },
        "manual_focus_supported": True,
        "exposure_time_range": [1000, 100000000],
        "iso_range": [50, 3200]
    })
    
    res = decoder.decode(raw)
    assert res["type"] == "CAPABILITIES"
    caps = res["capabilities"]
    
    assert caps.camera_stream_key == CameraStreamKey("DEV1", "0", "0", "2")
    assert caps.manual_focus_supported is True
    assert caps.exposure_time_range == (1000, 100000000)
    assert caps.iso_range == (50, 3200)

def test_control_response_parsing():
    decoder = ControlMessageDecoder()
    raw = json.dumps({
        "message_type": "CONTROL_RESPONSE",
        "request_id": "REQ-123",
        "control_type": "FOCUS",
        "requested": 3.2,
        "applied": 3.18,
        "status": "APPLIED"
    })
    
    res = decoder.decode(raw)
    assert res["type"] == "RESPONSE"
    assert res["request_id"] == "REQ-123"
    assert res["status"] == ControlStateStatus.APPLIED
    assert res["applied"] == 3.18

def test_focus_metric_tenengrad():
    # Uniform image -> 0 gradient energy
    arr_uniform = np.ones((10, 10, 3), dtype=np.uint8) * 100
    score_u = calculate_focus_metric(arr_uniform, method="TENENGRAD")
    assert score_u == 0.0
    
    # High contrast image -> high gradient energy
    arr_contrast = np.zeros((10, 10, 3), dtype=np.uint8)
    arr_contrast[::2, ::2] = [255, 255, 255]
    score_c = calculate_focus_metric(arr_contrast, method="TENENGRAD")
    assert score_c > 0.0

def test_focus_metric_laplacian():
    arr_uniform = np.ones((10, 10, 3), dtype=np.uint8) * 100
    score_u = calculate_focus_metric(arr_uniform, method="LAPLACIAN_VARIANCE")
    assert score_u == 0.0
    
    arr_contrast = np.zeros((10, 10, 3), dtype=np.uint8)
    arr_contrast[::2, ::2] = [255, 255, 255]
    score_c = calculate_focus_metric(arr_contrast, method="LAPLACIAN_VARIANCE")
    assert score_c > 0.0
