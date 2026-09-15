import time
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QGroupBox, QComboBox, QSlider, QScrollArea)
from PySide6.QtCore import Qt, QTimer

from virtual_lab.instruments.control import CameraCapabilities, ControlState, ControlStateStatus, ControlPreset
from virtual_lab.instruments.optics import generate_id
from virtual_lab.instruments.camera import CameraStreamKey

class DebouncedSlider(QWidget):
    def __init__(self, label: str, min_val: int, max_val: int, debounce_ms: int = 200, parent=None):
        super().__init__(parent)
        self.label_text = label
        
        layout = QVBoxLayout(self)
        
        # Headers
        self.lbl_title = QLabel(f"{label}")
        self.lbl_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.lbl_title)
        
        info_layout = QHBoxLayout()
        self.lbl_req = QLabel("Req: --")
        self.lbl_app = QLabel("App: --")
        self.lbl_status = QLabel("Status: --")
        
        info_layout.addWidget(self.lbl_req)
        info_layout.addWidget(self.lbl_app)
        info_layout.addWidget(self.lbl_status)
        layout.addLayout(info_layout)
        
        # Slider
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(min_val)
        self.slider.setMaximum(max_val)
        layout.addWidget(self.slider)
        
        # Debounce timer
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(debounce_ms)
        self.timer.timeout.connect(self._on_timeout)
        
        self.slider.valueChanged.connect(self._on_value_changed)
        
        # State
        self.current_requested = None
        self.current_applied = None
        
        # Callbacks
        self.on_request = None
        
    def _on_value_changed(self, value):
        self.current_requested = value
        self.lbl_req.setText(f"Req: {value}")
        self.timer.start()
        
    def _on_timeout(self):
        if self.on_request:
            self.on_request(self.current_requested)
            
    def update_applied(self, applied_value: Any, status: ControlStateStatus):
        self.current_applied = applied_value
        self.lbl_app.setText(f"App: {applied_value}")
        self.lbl_status.setText(f"Status: {status.value}")

class ControlPanel(QWidget):
    def __init__(self, gateway, parent=None):
        super().__init__(parent)
        self.gateway = gateway
        self.capabilities: Optional[CameraCapabilities] = None
        
        self.requests: Dict[str, ControlState] = {}
        
        self._init_ui()
        
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        
        self.lbl_header = QLabel("SCIENTIFIC CAMERA CONTROLS")
        self.lbl_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.scroll_layout.addWidget(self.lbl_header)
        
        self.lbl_camera = QLabel("Camera: None")
        self.lbl_camera.setStyleSheet("color: #94a3b8;")
        self.scroll_layout.addWidget(self.lbl_camera)
        
        # Focus
        self.group_focus = QGroupBox("FOCUS")
        self.focus_layout = QVBoxLayout(self.group_focus)
        self.scroll_layout.addWidget(self.group_focus)
        
        # Exposure
        self.group_exp = QGroupBox("EXPOSURE")
        self.exp_layout = QVBoxLayout(self.group_exp)
        self.scroll_layout.addWidget(self.group_exp)
        
        # AWB
        self.group_awb = QGroupBox("WHITE BALANCE")
        self.awb_layout = QVBoxLayout(self.group_awb)
        self.scroll_layout.addWidget(self.group_awb)
        
        self.scroll_layout.addStretch()
        
        scroll.setWidget(self.scroll_content)
        main_layout.addWidget(scroll)
        
        # Connect signals
        self.gateway.controlCapabilityReceived.connect(self._on_capabilities)
        self.gateway.controlMessageReceived.connect(self._on_response)
        
        self.controls = {}

    def _on_capabilities(self, caps: CameraCapabilities):
        self.capabilities = caps
        k = caps.camera_stream_key
        self.lbl_camera.setText(f"Camera: {k.camera_id} (Log: {k.logical_camera_id}, Phys: {k.physical_camera_id})")
        self._build_controls()
        
    def _build_controls(self):
        # Clear existing
        for layout in [self.focus_layout, self.exp_layout, self.awb_layout]:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                    
        self.controls.clear()
        
        caps = self.capabilities
        if not caps: return
        
        # Focus
        if caps.manual_focus_supported:
            slider = DebouncedSlider("Manual Focus (D)", 0, int(caps.minimum_focus_distance * 100))
            slider.on_request = lambda val: self._send_request("FOCUS", val / 100.0)
            self.focus_layout.addWidget(slider)
            self.controls["FOCUS"] = slider
        else:
            self.focus_layout.addWidget(QLabel("Manual Focus not supported"))
            
        # Exposure
        if caps.manual_sensor_supported:
            min_exp = caps.exposure_time_range[0] // 1000000 # ms
            max_exp = caps.exposure_time_range[1] // 1000000 # ms
            
            exp_slider = DebouncedSlider("Exposure Time (ms)", min_exp, max_exp)
            exp_slider.on_request = lambda val: self._send_request("EXPOSURE", val * 1000000)
            self.exp_layout.addWidget(exp_slider)
            self.controls["EXPOSURE"] = exp_slider
            
            min_iso = caps.iso_range[0]
            max_iso = caps.iso_range[1]
            iso_slider = DebouncedSlider("ISO", min_iso, max_iso)
            iso_slider.on_request = lambda val: self._send_request("ISO", val)
            self.exp_layout.addWidget(iso_slider)
            self.controls["ISO"] = iso_slider
            
        else:
            self.exp_layout.addWidget(QLabel("Manual Sensor not supported"))

    def _send_request(self, control_type: str, value: Any):
        req_id = generate_id("REQ")
        state = ControlState(
            request_id=req_id,
            control_type=control_type,
            requested_value=value,
            status=ControlStateStatus.QUEUED,
            requested_utc=int(time.time() * 1000)
        )
        self.requests[req_id] = state
        
        msg = {
            "message_type": "CONTROL_REQUEST",
            "request_id": req_id,
            "control_type": control_type,
            "requested": value
        }
        self.gateway.send_control_message(msg)
        state.status = ControlStateStatus.SENT
        
    def _on_response(self, response: dict):
        req_id = response.get("request_id")
        if req_id not in self.requests:
            return # Ignore unmatched
            
        state = self.requests[req_id]
        state.applied_value = response.get("applied")
        state.status = response.get("status")
        state.error_message = response.get("error_message")
        state.confirmed_utc = int(time.time() * 1000)
        
        ctrl_type = state.control_type
        if ctrl_type in self.controls:
            self.controls[ctrl_type].update_applied(state.applied_value, state.status)
            
        if state.status.value == "APPLIED" or state.status.value == "REJECTED" or state.status.value == "FAILED":
            from virtual_lab.core.ledger import Actor
            payload = {
                "request_id": req_id,
                "camera_stream_key": {
                    "device_id": self.capabilities.camera_stream_key.device_id,
                    "camera_id": self.capabilities.camera_stream_key.camera_id,
                    "logical_camera_id": self.capabilities.camera_stream_key.logical_camera_id,
                    "physical_camera_id": self.capabilities.camera_stream_key.physical_camera_id
                } if self.capabilities else None,
                "control_type": ctrl_type,
                "requested": state.requested_value,
                "applied": state.applied_value,
                "status": state.status.value,
                "error_message": state.error_message,
                "requested_utc": state.requested_utc,
                "confirmed_utc": state.confirmed_utc
            }
            
            # Invalidate calibration if scale-affecting settings changed
            if ctrl_type in ["RESOLUTION", "ZOOM", "CROP"] and state.status.value == "APPLIED":
                # Assuming workspace parent has optical_panel reference
                parent_opt = self.parent()
                if hasattr(parent_opt, "current_calibration") and parent_opt.current_calibration:
                    parent_opt.lbl_calib.setText("Calibration: STALE - REVALIDATION REQUIRED")
                    parent_opt.lbl_calib.setStyleSheet("color: #ef4444; font-weight: bold;")
            
            # Use gateway's parent (InstrumentsWorkspace) to get ledger
            if hasattr(self.gateway.parent(), "workspace"):
                self.gateway.parent().workspace.ledger.append(
                    event_id=generate_id("EVT"),
                    actor=Actor(type="SYSTEM", id="virtual_lab"),
                    event_type="INSTRUMENT_CAMERA_CONTROL_APPLIED",
                    payload=payload
                )
