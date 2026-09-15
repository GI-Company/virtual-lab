import json
import pytest
import struct
from virtual_lab.instruments.transport.packet_parser import PacketDecoder, CameraFrameDecoder
from virtual_lab.instruments.camera import CameraStreamKey

def test_sensor_continuous_preview():
    decoder = PacketDecoder()
    raw = json.dumps({
        "device_id": "TEST-1",
        "session_id": "PREVIEW",
        "measurement_type": "ACCELERATION",
        "sensor_id": "accel",
        "sequence": 1,
        "device_timestamp_ns": 1000,
        "values": {"ax": 0.0, "ay": 9.8, "az": 0.0},
        "units": {"ax": "m/s^2", "ay": "m/s^2", "az": "m/s^2"}
    })
    
    m = decoder.decode(raw, "PREVIEW")
    assert m.quantity == "ACCELERATION"
    assert m.session_id == "PREVIEW"

def test_canonical_illuminance_field():
    decoder = PacketDecoder()
    raw = json.dumps({
        "device_id": "TEST-1",
        "session_id": "PREVIEW",
        "measurement_type": "ILLUMINANCE",
        "sensor_id": "light",
        "sequence": 1,
        "device_timestamp_ns": 1000,
        "values": {"illuminance": 42.0},
        "units": {"illuminance": "lx"}
    })
    
    m = decoder.decode(raw, "PREVIEW")
    assert m.quantity == "ILLUMINANCE"
    assert m.values["illuminance"] == 42.0

def test_interleaved_sensor_modalities():
    decoder = PacketDecoder()
    
    raw_accel = json.dumps({
        "measurement_type": "ACCELERATION",
        "values": {"ax": 0.0, "ay": 9.8, "az": 0.0},
        "units": {"ax": "m/s^2", "ay": "m/s^2", "az": "m/s^2"}
    })
    
    raw_mag = json.dumps({
        "measurement_type": "MAGNETIC_FIELD",
        "values": {"bx": 1.0, "by": 2.0, "bz": 3.0},
        "units": {"bx": "uT", "by": "uT", "bz": "uT"}
    })
    
    m1 = decoder.decode(raw_accel, "SESS-1")
    m2 = decoder.decode(raw_mag, "SESS-1")
    
    assert m1.quantity == "ACCELERATION"
    assert m2.quantity == "MAGNETIC_FIELD"

def build_camera_frame(metadata, jpeg_bytes=b"jpeg_data"):
    meta_bytes = json.dumps(metadata).encode('utf-8')
    meta_len = len(meta_bytes)
    return struct.pack(">I", meta_len) + meta_bytes + jpeg_bytes

def get_base_meta():
    return {
        "schema_version": "1",
        "message_type": "CAMERA_PREVIEW_FRAME",
        "device_id": "DEV1",
        "camera_id": "0",
        "width": 1280,
        "height": 720
    }

def test_valid_binary_frame_decode():
    decoder = CameraFrameDecoder()
    meta = get_base_meta()
    raw = build_camera_frame(meta)
    
    res = decoder.decode(raw)
    assert res.message_type == "CAMERA_PREVIEW_FRAME"
    assert res.jpeg_bytes == b"jpeg_data"
    assert res.stream_key == CameraStreamKey("DEV1", "0", None, None)

def test_malformed_metadata_length():
    decoder = CameraFrameDecoder()
    with pytest.raises(ValueError, match="Frame truncated"):
        decoder.decode(b"\x00\x00") # only 2 bytes

def test_truncated_metadata():
    decoder = CameraFrameDecoder()
    meta_bytes = b'{"key":'
    raw = struct.pack(">I", 100) + meta_bytes + b"jpeg_data"
    with pytest.raises(ValueError, match="Frame truncated"):
        decoder.decode(raw)

def test_empty_jpeg():
    decoder = CameraFrameDecoder()
    meta = get_base_meta()
    raw = build_camera_frame(meta, b"")
    with pytest.raises(ValueError, match="Empty JPEG payload"):
        decoder.decode(raw)

def test_oversized_frame_rejection():
    decoder = CameraFrameDecoder()
    raw = b"\x00" * (10 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="Frame exceeds 10MB max size"):
        decoder.decode(raw)

def test_preview_vs_scientific_frame_message_type():
    decoder = CameraFrameDecoder()
    
    preview_meta = get_base_meta()
    scientific_meta = get_base_meta()
    scientific_meta["message_type"] = "CAMERA_SCIENTIFIC_FRAME"
    
    res_preview = decoder.decode(build_camera_frame(preview_meta))
    res_scientific = decoder.decode(build_camera_frame(scientific_meta))
    
    assert res_preview.message_type == "CAMERA_PREVIEW_FRAME"
    assert res_scientific.message_type == "CAMERA_SCIENTIFIC_FRAME"

def test_invalid_utf8_metadata():
    decoder = CameraFrameDecoder()
    # Create invalid utf-8 bytes
    invalid_utf8 = b'\xff\xfe\xfd'
    raw = struct.pack(">I", len(invalid_utf8)) + invalid_utf8 + b"jpeg_data"
    with pytest.raises(ValueError, match="Invalid metadata JSON"):
        decoder.decode(raw)

def test_invalid_json_metadata():
    decoder = CameraFrameDecoder()
    meta_bytes = b'{"missing_brace": 1'
    raw = struct.pack(">I", len(meta_bytes)) + meta_bytes + b"jpeg_data"
    with pytest.raises(ValueError, match="Invalid metadata JSON"):
        decoder.decode(raw)

def test_unsupported_schema_version():
    decoder = CameraFrameDecoder()
    meta = get_base_meta()
    meta["schema_version"] = "2"
    raw = build_camera_frame(meta)
    with pytest.raises(ValueError, match="Unsupported schema_version: 2"):
        decoder.decode(raw)

def test_unsupported_message_type():
    decoder = CameraFrameDecoder()
    meta = get_base_meta()
    meta["message_type"] = "UNKNOWN_FRAME"
    raw = build_camera_frame(meta)
    with pytest.raises(ValueError, match="Unsupported message_type: UNKNOWN_FRAME"):
        decoder.decode(raw)

def test_invalid_resolution():
    decoder = CameraFrameDecoder()
    meta = get_base_meta()
    meta["width"] = 0
    raw = build_camera_frame(meta)
    with pytest.raises(ValueError, match="Invalid resolution: 0x720"):
        decoder.decode(raw)

def test_camera_stream_key_equality():
    k1 = CameraStreamKey("DEV1", "0", "0", "2")
    k2 = CameraStreamKey("DEV1", "0", "0", "2")
    k3 = CameraStreamKey("DEV1", "0", "0", "3")
    
    assert k1 == k2
    assert k1 != k3
    
    s = set()
    s.add(k1)
    assert k2 in s
    assert k3 not in s
