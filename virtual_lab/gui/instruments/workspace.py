from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QGroupBox, QSplitter, QFrame, QComboBox, QStackedWidget)
from PySide6.QtCore import Qt, QTimer
import pyqtgraph as pg
import math
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from virtual_lab.instruments.transport.gateway import InstrumentGateway
from virtual_lab.instruments.transport.discovery import InstrumentDiscoveryService, DiscoveryStatus
from virtual_lab.instruments.storage import JsonlMeasurementStore
from virtual_lab.instruments.measurements import Measurement
from virtual_lab.instruments.camera import CameraFrame, CameraStreamKey, CameraStreamState
from virtual_lab.core.ledger import Actor
from virtual_lab.version import __version__
from virtual_lab.gui.instruments.optical_panel import OpticalPanel

@dataclass
class SensorStreamState:
    measurement_type: str
    total_packets: int = 0
    total_dropped: int = 0
    last_sequence: Optional[int] = None
    packet_timestamps: List[int] = field(default_factory=list)
    ring_buffer_time: List[float] = field(default_factory=list)
    ring_buffer_v1: List[float] = field(default_factory=list)
    ring_buffer_v2: List[float] = field(default_factory=list)
    ring_buffer_v3: List[float] = field(default_factory=list)
    ring_buffer_mag: List[float] = field(default_factory=list)
    latest_measurement: Optional[Measurement] = None

    def calculate_rate(self) -> float:
        if len(self.packet_timestamps) < 2: return 0.0
        t_recent = self.packet_timestamps[-100:]
        if len(t_recent) < 2: return 0.0
        dt = (t_recent[-1] - t_recent[0]) / 1e9
        if dt <= 0: return 0.0
        return len(t_recent) / dt

class InstrumentsWorkspace(QWidget):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.gateway = InstrumentGateway(port=8765, parent=self)
        self.discovery = InstrumentDiscoveryService(port=8765)
        self.store = JsonlMeasurementStore()
        
        self.current_state = "DISCONNECTED" # DISCONNECTED, CONNECTED, RECORDING
        self.current_instrument = None
        self.current_session = None
        
        self.streams: Dict[str, SensorStreamState] = {}
        self.max_display_samples = 3000
        
        # Camera State
        self.observed_camera_streams: Dict[CameraStreamKey, CameraStreamState] = {}
        self.selected_camera_key: Optional[CameraStreamKey] = None
        self.pending_camera_key: Optional[CameraStreamKey] = None
        self.last_displayed_camera_frame: Optional[CameraFrame] = None
        
        self.pending_capture_request_id: Optional[str] = None
        
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Header
        header = QHBoxLayout()
        lbl_title = QLabel("INSTRUMENTS")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #8b9bb4;")
        header.addWidget(lbl_title)
        header.addStretch()
        self.lbl_status = QLabel("● DISCONNECTED")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #ef4444;")
        header.addWidget(self.lbl_status)
        main_layout.addLayout(header)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # Left Panel (Devices)
        self.panel_left = QWidget()
        left_layout = QVBoxLayout(self.panel_left)
        
        self.group_devices = QGroupBox("DEVICES")
        devices_layout = QVBoxLayout(self.group_devices)
        
        self.lbl_gateway_info = QLabel("Gateway Disabled")
        self.lbl_gateway_info.setStyleSheet("font-family: monospace; color: #94a3b8;")
        devices_layout.addWidget(self.lbl_gateway_info)
        
        # Separator line
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        line1.setStyleSheet("background-color: #334155; margin: 10px 0;")
        devices_layout.addWidget(line1)
        
        self.lbl_device_info = QLabel("No Instrument Connected")
        devices_layout.addWidget(self.lbl_device_info)
        
        # Selector
        self.combo_sensor = QComboBox()
        self.combo_sensor.addItem("No data received")
        self.combo_sensor.currentTextChanged.connect(self._on_sensor_selected)
        devices_layout.addWidget(QLabel("Live Sensor:"))
        devices_layout.addWidget(self.combo_sensor)
        
        self.lbl_values = QLabel()
        self.lbl_values.setStyleSheet("font-family: monospace;")
        devices_layout.addWidget(self.lbl_values)
        
        # Camera Selector
        self.combo_camera = QComboBox()
        self.combo_camera.addItem("No camera data")
        self.combo_camera.currentTextChanged.connect(self._on_camera_selected)
        devices_layout.addWidget(QLabel("Live Camera:"))
        devices_layout.addWidget(self.combo_camera)
        
        # Diagnostics
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        line2.setStyleSheet("background-color: #334155; margin: 10px 0;")
        devices_layout.addWidget(line2)
        
        self.lbl_diagnostics = QLabel("Diagnostics:\n-")
        self.lbl_diagnostics.setStyleSheet("font-family: monospace; color: #64748b; font-size: 10px;")
        devices_layout.addWidget(self.lbl_diagnostics)
        
        self.btn_gateway = QPushButton("Enable Instrument Gateway")
        self.btn_gateway.clicked.connect(self._toggle_gateway)
        devices_layout.addWidget(self.btn_gateway)
        
        self.btn_session = QPushButton("START SESSION")
        self.btn_session.setObjectName("primary")
        self.btn_session.clicked.connect(self._toggle_session)
        self.btn_session.setEnabled(False)
        devices_layout.addWidget(self.btn_session)
        
        # Mode Selector
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("CAMERA")
        self.combo_mode.addItem("MICROSCOPE")
        self.combo_mode.currentTextChanged.connect(self._on_mode_changed)
        devices_layout.addWidget(QLabel("Acquisition Mode:"))
        devices_layout.addWidget(self.combo_mode)
        
        self.btn_capture = QPushButton("CAPTURE SCIENTIFIC FRAME")
        self.btn_capture.setEnabled(False)
        self.btn_capture.clicked.connect(self._trigger_scientific_capture)
        devices_layout.addWidget(self.btn_capture)
        
        devices_layout.addStretch()
        left_layout.addWidget(self.group_devices)
        splitter.addWidget(self.panel_left)
        
        # Right Panel (Trace / Microscope)
        self.panel_right = QWidget()
        right_layout = QVBoxLayout(self.panel_right)
        
        self.stack_right = QStackedWidget()
        
        # Mode 1: Trace View
        self.trace_view = QWidget()
        trace_layout = QVBoxLayout(self.trace_view)
        
        self.group_trace = QGroupBox("LIVE TRACE")
        trace_inner_layout = QVBoxLayout(self.group_trace)
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#0f172a')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()
        self.curve_v1 = self.plot_widget.plot(pen=pg.mkPen('r', width=2), name="X")
        self.curve_v2 = self.plot_widget.plot(pen=pg.mkPen('g', width=2), name="Y")
        self.curve_v3 = self.plot_widget.plot(pen=pg.mkPen('b', width=2), name="Z")
        self.curve_mag = self.plot_widget.plot(pen=pg.mkPen('w', width=2, style=Qt.DashLine), name="Mag")
        
        trace_inner_layout.addWidget(self.plot_widget)
        
        self.lbl_camera_view = QLabel("No Camera Feed")
        self.lbl_camera_view.setAlignment(Qt.AlignCenter)
        self.lbl_camera_view.setStyleSheet("background-color: #000; color: #64748b; font-family: monospace;")
        self.lbl_camera_view.setMinimumHeight(300)
        trace_inner_layout.addWidget(self.lbl_camera_view)
        
        self.lbl_camera_stats = QLabel("")
        self.lbl_camera_stats.setStyleSheet("font-family: monospace; color: #94a3b8;")
        trace_inner_layout.addWidget(self.lbl_camera_stats)
        
        self.lbl_session_status = QLabel("Preview Mode")
        self.lbl_session_status.setStyleSheet("color: #94a3b8; font-family: monospace;")
        trace_inner_layout.addWidget(self.lbl_session_status)
        
        trace_layout.addWidget(self.group_trace)
        self.stack_right.addWidget(self.trace_view)
        
        # Mode 2: Microscope View
        self.optical_panel = OpticalPanel(self.workspace, self.gateway)
        self.stack_right.addWidget(self.optical_panel)
        
        right_layout.addWidget(self.stack_right)
        splitter.addWidget(self.panel_right)
        
        splitter.setSizes([350, 650])
        main_layout.addWidget(splitter)
        
        # Display Timer for 15 Hz redraw
        self.display_timer = QTimer(self)
        self.display_timer.setInterval(1000 // 15)
        self.display_timer.timeout.connect(self._update_ui)

    def _connect_signals(self):
        self.gateway.instrumentConnected.connect(self._on_instrument_connected)
        self.gateway.instrumentDisconnected.connect(self._on_instrument_disconnected)
        self.gateway.measurementReceived.connect(self._on_measurement)
        self.gateway.binaryMessageReceived.connect(self._on_binary_message)

    def _on_mode_changed(self, text):
        if text == "CAMERA":
            self.stack_right.setCurrentIndex(0)
        elif text == "MICROSCOPE":
            self.stack_right.setCurrentIndex(1)
            
    def _on_sensor_selected(self, text):
        pass # Will redraw on next UI tick
        
    def _on_camera_selected(self, text):
        if text == "No camera data" or not text:
            return
            
        # Parse the key back out of the combo box text
        # Format: "Dev: {dev} | Cam: {cam} | Log: {log} | Phys: {phys}"
        try:
            parts = [p.split(": ")[1].strip() for p in text.split(" | ")]
            if len(parts) == 4:
                dev, cam, log, phys = parts
                log = log if log != "None" else None
                phys = phys if phys != "None" else None
                new_key = CameraStreamKey(dev, cam, log, phys)
                
                if self.selected_camera_key != new_key:
                    self.pending_camera_key = new_key
                    self.lbl_camera_view.setText("SWITCHING CAMERA...")
                    self.lbl_camera_view.setStyleSheet("background-color: #000; color: #f59e0b; font-weight: bold;")
        except Exception:
            pass

    def _toggle_gateway(self):
        if self.current_state == "DISCONNECTED":
            if self.gateway.start():
                self.current_state = "LISTENING"
                self.btn_gateway.setText("Disable Instrument Gateway")
                self.lbl_status.setText("● LISTENING ON 8765")
                self.lbl_status.setStyleSheet("font-weight: bold; color: #f59e0b;")
                self.discovery.start()
                self._update_diagnostics_ui()
            else:
                self.lbl_gateway_info.setText("Gateway Start Failed: Could not bind to port 8765.")
        else:
            self.discovery.stop()
            self.gateway.stop()
            self.btn_gateway.setText("Enable Instrument Gateway")
            self.lbl_gateway_info.setText("Gateway Disabled")
            self._set_disconnected_state()

    def _update_diagnostics_ui(self):
        d_status = self.discovery.status()
        addresses = self.discovery.advertised_addresses()
        addr_str = addresses[0] if addresses else "NONE"
        svc_name = self.discovery.registered_name()
        
        info = (
            f"INSTRUMENT GATEWAY\n\n"
            f"WebSocket\n● LISTENING\n\n"
            f"Bind\n0.0.0.0:8765\n\n"
            f"Sensor path\n/sensors\n\n"
            f"Discovery\n● {d_status.value}\n\n"
            f"Service\n{svc_name}\n\n"
            f"mDNS type\n_virtuallab._tcp.local.\n\n"
            f"LAN address\n{addr_str}\n\n"
            f"Protocol\n1\n\n"
            f"VirtualLab\n{__version__}"
        )
        self.lbl_gateway_info.setText(info)
        
        if d_status == DiscoveryStatus.FAILED:
            self.lbl_gateway_info.setStyleSheet("font-family: monospace; color: #ef4444;")
        else:
            self.lbl_gateway_info.setStyleSheet("font-family: monospace; color: #94a3b8;")

    def _set_disconnected_state(self):
        self.current_state = "DISCONNECTED"
        self.current_instrument = None
        self.lbl_status.setText("● DISCONNECTED")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #ef4444;")
        self.lbl_device_info.setText("No Instrument Connected")
        self.btn_session.setEnabled(False)
        self.btn_session.setText("START SESSION")
        self.display_timer.stop()
        self.lbl_values.clear()
        
        self.streams.clear()
        self.combo_sensor.clear()
        self.combo_sensor.addItem("No data received")
        
        self.observed_camera_streams.clear()
        self.selected_camera_key = None
        self.pending_camera_key = None
        self.last_displayed_camera_frame = None
        self.pending_capture_request_id = None
        self.combo_camera.clear()
        self.combo_camera.addItem("No camera data")
        self.lbl_camera_view.setText("No Camera Feed")
        self.lbl_camera_stats.clear()
        
        self.curve_v1.setData([], [])
        self.curve_v2.setData([], [])
        self.curve_v3.setData([], [])
        self.curve_mag.setData([], [])
        self.lbl_session_status.setText("Preview Mode")
        
        if self.current_session:
            self._stop_session(reason="Instrument disconnected mid-session")

    def _on_instrument_connected(self, inst_id, address):
        self.current_state = "CONNECTED"
        self.current_instrument = inst_id
        self.lbl_status.setText("● CONNECTED")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #22c55e;")
        self.lbl_device_info.setText(f"<b>{inst_id}</b><br/>UNVERIFIED DEVICE IDENTITY<br/>Address: {address}")
        self.btn_session.setEnabled(True)
        self.btn_capture.setEnabled(True)
        self.display_timer.start()
        
        self.workspace.ledger.append(
            event_id=f"EVT-{int(time.time()*1000)}",
            actor=Actor(type="SYSTEM", id="virtual_lab"),
            event_type="INSTRUMENT_CONNECTED",
            payload={"instrument_id": inst_id, "address": address}
        )

    def _on_instrument_disconnected(self, inst_id):
        self.workspace.ledger.append(
            event_id=f"EVT-{int(time.time()*1000)}",
            actor=Actor(type="SYSTEM", id="virtual_lab"),
            event_type="INSTRUMENT_DISCONNECTED",
            payload={"instrument_id": inst_id}
        )
        self._set_disconnected_state()

    def _on_measurement(self, measurement: Measurement):
        mt = measurement.quantity
        
        if mt not in self.streams:
            self.streams[mt] = SensorStreamState(measurement_type=mt)
            if self.combo_sensor.itemText(0) == "No data received":
                self.combo_sensor.clear()
            self.combo_sensor.addItem(mt)
            
        stream = self.streams[mt]
        stream.latest_measurement = measurement
        stream.total_packets += 1
        stream.packet_timestamps.append(measurement.device_timestamp_ns)
        
        if stream.last_sequence is not None:
            diff = measurement.sequence - stream.last_sequence
            if diff > 1:
                stream.total_dropped += (diff - 1)
        stream.last_sequence = measurement.sequence
        
        if len(stream.packet_timestamps) > 1000:
            stream.packet_timestamps.pop(0)
            
        if self.current_state == "RECORDING":
            self.store.append(measurement)
            
        if len(stream.ring_buffer_time) > self.max_display_samples:
            stream.ring_buffer_time.pop(0)
            stream.ring_buffer_v1.pop(0)
            if stream.ring_buffer_v2: stream.ring_buffer_v2.pop(0)
            if stream.ring_buffer_v3: stream.ring_buffer_v3.pop(0)
            if stream.ring_buffer_mag: stream.ring_buffer_mag.pop(0)
            
        t = measurement.device_timestamp_ns / 1e9
        stream.ring_buffer_time.append(t)
        
        v = measurement.values
        if mt == "MAGNETIC_FIELD":
            stream.ring_buffer_v1.append(v.get("bx", 0.0))
            stream.ring_buffer_v2.append(v.get("by", 0.0))
            stream.ring_buffer_v3.append(v.get("bz", 0.0))
            b_mag = math.sqrt(v.get("bx",0.0)**2 + v.get("by",0.0)**2 + v.get("bz",0.0)**2)
            stream.ring_buffer_mag.append(b_mag)
        elif mt == "ACCELERATION":
            stream.ring_buffer_v1.append(v.get("ax", 0.0))
            stream.ring_buffer_v2.append(v.get("ay", 0.0))
            stream.ring_buffer_v3.append(v.get("az", 0.0))
        elif mt == "ANGULAR_VELOCITY":
            stream.ring_buffer_v1.append(v.get("wx", 0.0))
            stream.ring_buffer_v2.append(v.get("wy", 0.0))
            stream.ring_buffer_v3.append(v.get("wz", 0.0))
        elif mt == "ILLUMINANCE":
            stream.ring_buffer_v1.append(v.get("illuminance", 0.0))
        elif mt == "PRESSURE":
            stream.ring_buffer_v1.append(v.get("pressure", 0.0))

    def _on_binary_message(self, frame: CameraFrame):
        key = frame.stream_key
        
        if key not in self.observed_camera_streams:
            self.observed_camera_streams[key] = CameraStreamState(key=key)
            if self.combo_camera.itemText(0) == "No camera data":
                self.combo_camera.clear()
            key_text = f"Dev: {key.device_id} | Cam: {key.camera_id} | Log: {key.logical_camera_id} | Phys: {key.physical_camera_id}"
            self.combo_camera.addItem(key_text)
            
            # Auto-select the first camera observed if none selected
            if self.selected_camera_key is None and self.pending_camera_key is None:
                self.pending_camera_key = key
                
        state = self.observed_camera_streams[key]
        state.frames_received += 1
        
        # Check for sequence resets (epoch transition)
        if state.last_sequence is not None:
            if frame.frame_sequence < state.last_sequence:
                # Likely an epoch restart
                state.epoch += 1
            elif frame.frame_sequence == state.last_sequence:
                state.duplicates += 1
            else:
                diff = frame.frame_sequence - state.last_sequence
                if diff > 1:
                    state.dropped += (diff - 1)
        
        state.last_sequence = frame.frame_sequence
        state.last_device_timestamp_ns = frame.device_timestamp_ns
        
        if frame.message_type == "CAMERA_PREVIEW_FRAME":
            # Only render if it matches the selected or pending key
            if self.pending_camera_key == key:
                self.selected_camera_key = key
                self.pending_camera_key = None
                
            if self.selected_camera_key == key:
                self.last_displayed_camera_frame = frame
                
        elif frame.message_type == "CAMERA_SCIENTIFIC_FRAME":
            if self.pending_capture_request_id and frame.request_id != self.pending_capture_request_id:
                # Ignore, doesn't match our requested capture
                pass
            else:
                self.pending_capture_request_id = None
                self.btn_capture.setText("CAPTURE SCIENTIFIC FRAME")
                self.btn_capture.setEnabled(True)
                
                import hashlib
                import os
                
                jpeg_bytes = frame.jpeg_bytes
                sha256 = hashlib.sha256(jpeg_bytes).hexdigest()
                capture_id = f"CAP-{int(time.time()*1000)}"
                
                os.makedirs(".virtuallab/artifacts", exist_ok=True)
                artifact_path = f".virtuallab/artifacts/{capture_id}.jpg"
                with open(artifact_path, "wb") as f:
                    f.write(jpeg_bytes)
                    
                payload = {
                    "capture_id": capture_id,
                    "instrument_id": self.current_instrument,
                    "source_device_id": frame.device_id,
                    "camera_id": frame.camera_id,
                    "logical_camera_id": frame.logical_camera_id,
                    "physical_camera_id": frame.physical_camera_id,
                    "frame_sequence": frame.frame_sequence,
                    "device_timestamp_ns": frame.device_timestamp_ns,
                    "received_utc_ns": frame.received_utc_ns,
                    "width": frame.width,
                    "height": frame.height,
                    "encoding": frame.encoding,
                    "focal_length_mm": frame.focal_length_mm,
                    "exposure_time_ns": frame.exposure_time_ns,
                    "sensor_sensitivity_iso": frame.sensor_sensitivity_iso,
                    "focus_distance": frame.focus_distance,
                    "scientific_state": frame.scientific_state,
                    "acquisition_type": frame.acquisition_type,
                    "representation": frame.representation,
                    "request_id": frame.request_id,
                    "artifact_path": artifact_path,
                    "artifact_size_bytes": len(jpeg_bytes),
                    "sha256": sha256
                }
                
                # If we are in Microscope mode, attach the applied optical configuration
                if self.combo_mode.currentText() == "MICROSCOPE":
                    payload["optical_setup_id"] = self.optical_panel.current_setup.setup_id
                    if self.optical_panel.current_calibration:
                        payload["calibration_id"] = self.optical_panel.current_calibration.calibration_id
                
                self.workspace.ledger.append(
                    event_id=f"EVT-{int(time.time()*1000)}",
                    actor=Actor(type="SYSTEM", id="virtual_lab"),
                    event_type="SCIENTIFIC_CAMERA_FRAME_COMMITTED",
                    payload=payload
                )

        # Route frame to OpticalPanel if active
        if self.combo_mode.currentText() == "MICROSCOPE":
            if self.selected_camera_key == key or self.pending_camera_key == key:
                self.optical_panel.process_live_frame(frame)

    def _update_ui(self):
        # Diagnostics
        parser = self.gateway.decoder
        cam_parser = self.gateway.camera_decoder
        diag_text = (
            f"--- SENSORS ---\n"
            f"Raw pkts: {parser.total_received}\n"
            f"Decoded:  {parser.total_decoded}\n"
            f"Rejected: {parser.total_rejected}\n"
            f"Last typ: {parser.last_measurement_type}\n"
            f"Last err: {parser.last_error or 'None'}\n\n"
            f"--- CAMERA ---\n"
            f"Conn:     {len(self.gateway.camera_clients)}\n"
            f"Msg Recv: {self.gateway.camera_binary_messages_received}\n"
            f"Decoded:  {cam_parser.total_decoded}\n"
            f"Rejected: {cam_parser.total_rejected}\n"
            f"Bytes:    {self.gateway.camera_bytes_received}\n"
            f"Last err: {cam_parser.last_error or 'None'}"
        )
        self.lbl_diagnostics.setText(diag_text)
        
        # Camera Rendering (bounded by UI thread)
        if self.last_displayed_camera_frame:
            frame = self.last_displayed_camera_frame
            from PySide6.QtGui import QPixmap, QImage
            image = QImage.fromData(frame.jpeg_bytes)
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                scaled = pixmap.scaled(self.lbl_camera_view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_camera_view.setPixmap(scaled)
                self.lbl_camera_view.setStyleSheet("") # Clear any switching style
                
            state = self.observed_camera_streams[frame.stream_key]
            
            stats = (
                f"Device: {frame.device_id}\n"
                f"Camera: {frame.camera_id} | Log: {frame.logical_camera_id} | Phys: {frame.physical_camera_id}\n"
                f"Res: {frame.width}x{frame.height} | Seq: {frame.frame_sequence} | Epoch: {state.epoch}\n"
                f"Frames: {state.frames_received} | Drop: {state.dropped} | Dup: {state.duplicates}\n"
                f"Lens: {frame.lens_facing} | Foc: {frame.focal_length_mm} | ISO: {frame.sensor_sensitivity_iso}\n"
                f"State: {frame.scientific_state} | Rep: {frame.representation}"
            )
            self.lbl_camera_stats.setText(stats)
            # Clear the reference so we don't re-render the same frame
            self.last_displayed_camera_frame = None
        
        # Trace and Values
        sel_mt = self.combo_sensor.currentText()
        if sel_mt in self.streams:
            stream = self.streams[sel_mt]
            if stream.ring_buffer_time:
                t0 = stream.ring_buffer_time[0]
                rel_t = [t - t0 for t in stream.ring_buffer_time]
                
                self.curve_v1.setData([], [])
                self.curve_v2.setData([], [])
                self.curve_v3.setData([], [])
                self.curve_mag.setData([], [])
                
                v1, v2, v3, mag = 0.0, 0.0, 0.0, 0.0
                if stream.ring_buffer_v1: v1 = stream.ring_buffer_v1[-1]
                if stream.ring_buffer_v2: v2 = stream.ring_buffer_v2[-1]
                if stream.ring_buffer_v3: v3 = stream.ring_buffer_v3[-1]
                if stream.ring_buffer_mag: mag = stream.ring_buffer_mag[-1]
                
                val_text = f"{sel_mt}\n\n"
                
                if sel_mt == "MAGNETIC_FIELD":
                    self.curve_v1.setData(rel_t, stream.ring_buffer_v1)
                    self.curve_v2.setData(rel_t, stream.ring_buffer_v2)
                    self.curve_v3.setData(rel_t, stream.ring_buffer_v3)
                    self.curve_mag.setData(rel_t, stream.ring_buffer_mag)
                    val_text += f"Bx      {v1:>+8.2f} µT    MEASURED\n"
                    val_text += f"By      {v2:>+8.2f} µT    MEASURED\n"
                    val_text += f"Bz      {v3:>+8.2f} µT    MEASURED\n\n"
                    val_text += f"|B|     {mag:>+8.2f} µT    DERIVED\n\n"
                elif sel_mt == "ACCELERATION":
                    self.curve_v1.setData(rel_t, stream.ring_buffer_v1)
                    self.curve_v2.setData(rel_t, stream.ring_buffer_v2)
                    self.curve_v3.setData(rel_t, stream.ring_buffer_v3)
                    val_text += f"Ax      {v1:>+8.2f} m/s²  MEASURED\n"
                    val_text += f"Ay      {v2:>+8.2f} m/s²  MEASURED\n"
                    val_text += f"Az      {v3:>+8.2f} m/s²  MEASURED\n\n"
                elif sel_mt == "ANGULAR_VELOCITY":
                    self.curve_v1.setData(rel_t, stream.ring_buffer_v1)
                    self.curve_v2.setData(rel_t, stream.ring_buffer_v2)
                    self.curve_v3.setData(rel_t, stream.ring_buffer_v3)
                    val_text += f"ωx      {v1:>+8.2f} rad/s MEASURED\n"
                    val_text += f"ωy      {v2:>+8.2f} rad/s MEASURED\n"
                    val_text += f"ωz      {v3:>+8.2f} rad/s MEASURED\n\n"
                elif sel_mt == "ILLUMINANCE":
                    self.curve_v1.setData(rel_t, stream.ring_buffer_v1)
                    val_text += f"Illum   {v1:>8.2f} lx    MEASURED\n\n"
                elif sel_mt == "PRESSURE":
                    self.curve_v1.setData(rel_t, stream.ring_buffer_v1)
                    val_text += f"Pressure{v1:>8.2f} hPa   MEASURED\n\n"
                    
                val_text += f"Rate      {stream.calculate_rate():>5.1f} Hz\n"
                val_text += f"Packets   {stream.total_packets:>5,d}\n"
                val_text += f"Dropped   {stream.total_dropped:>5,d}\n"
                
                self.lbl_values.setText(val_text)
                
        if self.current_state == "RECORDING":
            sess_txt = f"SESSION {self.current_session}\nRECORDING\n\n"
            for mt, st in self.streams.items():
                hz = st.calculate_rate()
                samples = self.store.sample_counts.get(mt, 0)
                if samples > 0:
                    sess_txt += f"{mt[:15]:<15} {hz:>5.1f} Hz {samples:>8,d} samples\n"
            self.lbl_session_status.setText(sess_txt)
        else:
            self.lbl_session_status.setText("Preview Mode")

    def _toggle_session(self):
        if self.current_state == "CONNECTED":
            self._start_session()
        elif self.current_state == "RECORDING":
            self._stop_session()

    def _start_session(self):
        dt_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.current_session = f"SES-{dt_str}"
        self.gateway.set_active_session(self.current_session)
        
        metadata = {
            "requested_rate_hz": "MULTI",
            "sensor": "MULTI"
        }
        
        self.store.begin(self.current_session, self.current_instrument, metadata)
        self.current_state = "RECORDING"
        self.btn_session.setText("STOP SESSION")
        self.lbl_session_status.setStyleSheet("color: #ef4444; font-weight: bold; font-family: monospace;")
        
        self.workspace.ledger.append(
            event_id=f"EVT-{int(time.time()*1000)}",
            actor=Actor(type="SYSTEM", id="virtual_lab"),
            event_type="MEASUREMENT_SESSION_CREATED",
            payload={"session_id": self.current_session, "instrument_id": self.current_instrument}
        )

    def _stop_session(self, reason=None):
        self.current_state = "CONNECTED" if self.gateway.sensor_clients else "DISCONNECTED"
        self.gateway.set_active_session("PREVIEW")
        self.btn_session.setText("START SESSION")
        self.lbl_session_status.setStyleSheet("color: #94a3b8; font-family: monospace;")
        
        if reason:
            self.store.abort(reason)
            self.workspace.ledger.append(
                event_id=f"EVT-{int(time.time()*1000)}",
                actor=Actor(type="SYSTEM", id="virtual_lab"),
                event_type="MEASUREMENT_SESSION_INTERRUPTED",
                payload={"session_id": self.current_session, "reason": reason}
            )
        else:
            total_dropped = {mt: st.total_dropped for mt, st in self.streams.items()}
            rejected = self.gateway.decoder.total_rejected
            commit_result = self.store.commit(dropped_counts=total_dropped, rejected_count=rejected)
            self.workspace.ledger.append(
                event_id=f"EVT-{int(time.time()*1000)}",
                actor=Actor(type="SYSTEM", id="virtual_lab"),
                event_type="RAW_SENSOR_ARTIFACT_COMMITTED",
                payload=commit_result
            )
            
            
        self.current_session = None

    def _trigger_scientific_capture(self):
        from virtual_lab.instruments.optics import generate_id
        if not self.gateway.control_clients:
            # We don't have a control connection, can't trigger capture
            return
            
        req_id = generate_id("CAP-REQ")
        self.pending_capture_request_id = req_id
        
        self.btn_capture.setText("CAPTURING...")
        self.btn_capture.setEnabled(False)
        
        msg = {
            "message_type": "CONTROL_REQUEST",
            "request_id": req_id,
            "control_type": "CAPTURE_SCIENTIFIC_FRAME",
            "requested": None
        }
        self.gateway.send_control_message(msg)
