import json
from typing import Dict, Any
from virtual_lab.instruments.transport.protocol_v1 import (
    CameraControlResult,
    CameraCapabilities,
    CameraState,
    ScientificCaptureResult,
    ScientificFrameAck,
    InstrumentDescriptor
)

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
                caps = CameraCapabilities.model_validate(data)
                result = {"type": "CAPABILITIES", "capabilities": caps}
            elif msg_type == "CAMERA_CONTROL_RESULT":
                res = CameraControlResult.model_validate(data)
                result = {"type": "CONTROL_RESULT", "result": res}
            elif msg_type == "CAMERA_STATE":
                state = CameraState.model_validate(data)
                result = {"type": "CAMERA_STATE", "state": state}
            elif msg_type == "SCIENTIFIC_CAPTURE_RESULT":
                cap_res = ScientificCaptureResult.model_validate(data)
                result = {"type": "SCIENTIFIC_CAPTURE_RESULT", "result": cap_res}
            elif msg_type == "INSTRUMENT_DESCRIPTOR":
                desc = InstrumentDescriptor.model_validate(data)
                result = {"type": "INSTRUMENT_DESCRIPTOR", "descriptor": desc}
            else:
                # We can handle more types if needed, but these are the main ones Desktop receives.
                # Just return raw dict for unknown types so gateway can inspect if necessary.
                result = {"type": "UNKNOWN", "raw": data}
                
            self.total_decoded += 1
            return result
        except Exception as e:
            self.total_rejected += 1
            self.last_error = str(e)
            raise
