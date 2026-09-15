import json
from typing import Dict, Any
from virtual_lab.instruments.camera import CameraStreamKey
from virtual_lab.instruments.control import CameraCapabilities, ControlStateStatus

class ControlMessageDecoder:
    def __init__(self):
        self.total_received = 0
        self.total_decoded = 0
        self.total_rejected = 0
        self.last_error = None

    def decode(self, raw_message: str) -> Dict[str, Any]:
        self.total_received += 1
        try:
            data = json.loads(raw_message)
            msg_type = data.get("message_type")
            
            if not msg_type:
                raise ValueError("Missing message_type")
                
            if msg_type == "CAMERA_CAPABILITIES":
                result = self._parse_capabilities(data)
            elif msg_type == "CONTROL_RESPONSE":
                result = self._parse_response(data)
            else:
                raise ValueError(f"Unsupported message_type: {msg_type}")
                
            self.total_decoded += 1
            return result
        except Exception as e:
            self.total_rejected += 1
            self.last_error = str(e)
            raise

    def _parse_capabilities(self, data: Dict[str, Any]) -> Dict[str, Any]:
        key_data = data.get("camera_stream_key", {})
        key = CameraStreamKey(
            device_id=key_data.get("device_id", "UNKNOWN"),
            camera_id=key_data.get("camera_id", "0"),
            logical_camera_id=key_data.get("logical_camera_id"),
            physical_camera_id=key_data.get("physical_camera_id")
        )
        
        caps = CameraCapabilities(camera_stream_key=key)
        
        caps.manual_focus_supported = data.get("manual_focus_supported", False)
        caps.minimum_focus_distance = data.get("minimum_focus_distance", 0.0)
        caps.af_modes = data.get("af_modes", [])
        
        caps.manual_sensor_supported = data.get("manual_sensor_supported", False)
        exposure_range = data.get("exposure_time_range", [0, 0])
        caps.exposure_time_range = (exposure_range[0], exposure_range[1])
        
        iso_range = data.get("iso_range", [0, 0])
        caps.iso_range = (iso_range[0], iso_range[1])
        
        fd_range = data.get("frame_duration_range", [0, 0])
        caps.frame_duration_range = (fd_range[0], fd_range[1])
        
        caps.ae_modes = data.get("ae_modes", [])
        ae_comp = data.get("ae_compensation_range", [0, 0])
        caps.ae_compensation_range = (ae_comp[0], ae_comp[1])
        caps.ae_compensation_step = data.get("ae_compensation_step", 0.0)
        
        caps.awb_modes = data.get("awb_modes", [])
        caps.awb_lock_supported = data.get("awb_lock_supported", False)
        
        caps.fps_ranges = [tuple(r) for r in data.get("fps_ranges", [])]
        caps.resolutions = [tuple(r) for r in data.get("resolutions", [])]
        
        zr = data.get("zoom_ratio_range", [1.0, 1.0])
        caps.zoom_ratio_range = (zr[0], zr[1])
        
        caps.stabilization_modes = data.get("stabilization_modes", [])
        caps.torch_supported = data.get("torch_supported", False)
        caps.raw_capability = data.get("raw_capability", False)
        
        return {"type": "CAPABILITIES", "capabilities": caps}

    def _parse_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        req_id = data.get("request_id")
        if not req_id:
            raise ValueError("Missing request_id in CONTROL_RESPONSE")
            
        status_str = data.get("status", "FAILED")
        try:
            status = ControlStateStatus(status_str)
        except ValueError:
            status = ControlStateStatus.FAILED
            
        return {
            "type": "RESPONSE",
            "request_id": req_id,
            "control_type": data.get("control_type", "UNKNOWN"),
            "requested": data.get("requested"),
            "applied": data.get("applied"),
            "status": status,
            "error_message": data.get("error_message")
        }
