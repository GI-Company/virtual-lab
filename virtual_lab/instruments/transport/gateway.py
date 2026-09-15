import json
import time
from datetime import datetime, timezone
from PySide6.QtCore import QObject, Signal
from PySide6.QtWebSockets import QWebSocketServer, QWebSocket

from virtual_lab.instruments.measurements import Measurement, ScientificState

from virtual_lab.instruments.transport.packet_parser import PacketDecoder

class InstrumentGateway(QObject):
    measurementReceived = Signal(object)
    binaryMessageReceived = Signal(object)
    instrumentConnected = Signal(str, str) # instrument_id, address
    instrumentDisconnected = Signal(str)
    gatewayError = Signal(str)
    controlMessageReceived = Signal(object)
    controlCapabilityReceived = Signal(object)

    def __init__(self, port=8765, parent=None):
        super().__init__(parent)
        self.port = port
        self.server = QWebSocketServer("VirtualLab Instrument Gateway", QWebSocketServer.NonSecureMode, self)
        self.server.newConnection.connect(self._on_new_connection)
        
        self.sensor_clients = []
        self.camera_clients = []
        self.control_clients = []
        
        self.decoder = PacketDecoder()
        from virtual_lab.instruments.transport.packet_parser import CameraFrameDecoder
        self.camera_decoder = CameraFrameDecoder()
        
        from virtual_lab.instruments.transport.control_parser import ControlMessageDecoder
        self.control_decoder = ControlMessageDecoder()
        
        self.active_session_id = "PREVIEW"
        
        self.camera_binary_messages_received = 0
        self.camera_bytes_received = 0

    def start(self) -> bool:
        from PySide6.QtNetwork import QHostAddress
        if self.server.listen(QHostAddress.Any, self.port):
            return True
        else:
            self.gatewayError.emit(f"Failed to start server on port {self.port}")
            return False

    def stop(self):
        for client in self.sensor_clients + self.camera_clients + self.control_clients:
            client.close()
        self.server.close()

    def set_active_session(self, session_id: str):
        """Sets the authoritative session ID for incoming measurements."""
        self.active_session_id = session_id

    def _on_new_connection(self):
        client_socket = self.server.nextPendingConnection()
        
        path = client_socket.requestUrl().path()
        if path not in ["/sensors", "/camera", "/control"]:
            client_socket.close()
            client_socket.deleteLater()
            return
            
        if path == "/sensors":
            self.sensor_clients.append(client_socket)
            client_socket.textMessageReceived.connect(lambda msg, s=client_socket: self._on_message(s, msg))
        elif path == "/camera":
            self.camera_clients.append(client_socket)
            client_socket.binaryMessageReceived.connect(lambda msg, s=client_socket: self._on_binary_message(s, msg))
        elif path == "/control":
            self.control_clients.append(client_socket)
            client_socket.textMessageReceived.connect(lambda msg, s=client_socket: self._on_control_message(s, msg))
            
        client_socket.disconnected.connect(lambda s=client_socket, p=path: self._on_disconnect(s, p))

    def _on_message(self, socket, raw: str):
        try:
            measurement = self.decoder.decode(raw, self.active_session_id)
        except Exception as exc:
            self.gatewayError.emit(str(exc))
            return
            
        self.measurementReceived.emit(measurement)
        if len(self.sensor_clients) == 1 and self.decoder.total_decoded == 1:
            # Emit instrument connected on first valid packet
            self.instrumentConnected.emit(measurement.instrument_id, socket.peerAddress().toString())

    def _on_binary_message(self, socket, raw_bytes: bytes):
        self.camera_binary_messages_received += 1
        if hasattr(raw_bytes, 'data'):
            raw_bytes = raw_bytes.data()
        self.camera_bytes_received += len(raw_bytes)
        
        try:
            frame = self.camera_decoder.decode(raw_bytes)
        except Exception as exc:
            self.gatewayError.emit(str(exc))
            return
            
        self.binaryMessageReceived.emit(frame)

    def _on_control_message(self, socket, raw: str):
        try:
            result = self.control_decoder.decode(raw)
        except Exception as exc:
            self.gatewayError.emit(f"Control Parse Error: {str(exc)}")
            return
            
        if result["type"] == "CAPABILITIES":
            self.controlCapabilityReceived.emit(result["capabilities"])
        elif result["type"] == "RESPONSE":
            self.controlMessageReceived.emit(result)

    def _on_disconnect(self, socket, path):
        if path == "/sensors" and socket in self.sensor_clients:
            self.sensor_clients.remove(socket)
            if not self.sensor_clients:
                self.instrumentDisconnected.emit("ANDROID-DISCONNECTED")
        elif path == "/camera" and socket in self.camera_clients:
            self.camera_clients.remove(socket)
        elif path == "/control" and socket in self.control_clients:
            self.control_clients.remove(socket)
        socket.deleteLater()

    def send_control_message(self, msg: dict):
        if not self.control_clients:
            self.gatewayError.emit("CONTROL CHANNEL DISCONNECTED")
            return
        
        raw = json.dumps(msg)
        for client in self.control_clients:
            client.sendTextMessage(raw)
