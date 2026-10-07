import pytest
import json
from pathlib import Path
import numpy as np
from virtual_lab.instruments.transport.control_parser import ControlMessageDecoder
from virtual_lab.instruments.analysis import calculate_focus_metric

def test_capabilities_parsing():
    fixture = Path(__file__).resolve().parents[1] / "fixtures/protocol_v1/camera_capabilities.json"
    data = json.loads(fixture.read_text())
    data["manual_focus_supported"] = True
    data["exposure_time_range_ns"] = [1000, 100000000]
    data["iso_range"] = [50, 3200]

    res = ControlMessageDecoder().decode(json.dumps(data))
    assert res["type"] == "CAPABILITIES"
    caps = res["capabilities"]
    assert caps.device_id == "DEV-123"
    assert caps.camera_stream_key.camera_id == "0"
    assert caps.manual_focus_supported is True
    assert caps.exposure_time_range_ns == (1000, 100000000)
    assert caps.iso_range == (50, 3200)


def test_control_response_parsing():
    fixture = Path(__file__).resolve().parents[1] / "fixtures/protocol_v1/camera_control_result.json"
    res = ControlMessageDecoder().decode(fixture.read_text())
    assert res["type"] == "CONTROL_RESULT"
    result = res["result"]
    assert result.request_id == "REQ-1"
    assert result.overall_status == "APPLIED"
    assert result.parameter_results["exposure_time_ns"].applied == 1000

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
