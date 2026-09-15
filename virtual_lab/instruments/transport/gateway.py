import json
import time
import logging
from datetime import datetime, timezone
from PySide6.QtCore import QObject, Signal
from PySide6.QtWebSockets import QWebSocketServer, QWebSocket

from virtual_lab.instruments.measurements import Measurement
from virtual_lab.instruments.transport.packet_parser import PacketDecoder, CameraFrameDecoder
from virtual_lab.instruments.transport.control_parser import ControlMessageDecoder
from virtual_lab.instruments.connection import ConnectionRegistry, ChannelConnectionState, SensorChannelState, CameraChannelState, ControlChannelState
from virtual_lab.instruments.optics import generate_id

logger = logging.getLogger("virtuallab.gateway")
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)

class InstrumentGateway(QObject):
    # Public fine-grained signals
    channelConnected = Signal(str, str) # path, connection_id
    channelBound = Signal(str, str, str) # path, connection_id, device_id
    channelDisconnected = Signal(str, str) # path, connection_id
    channelError = Signal(str, str, str) # path, connection_id, error
    
    # Backward compatible projection signals
    instrumentConnected = Signal(str, str) # device_id, remote_addr
    instrumentDisconnected = Signal(str) # device_id
    
    # Data signals
    measurementReceived = Signal(object)
    binaryMessageReceived = Signal(object)
    controlMessageReceived = Signal(object)
    controlCapabilityReceived = Signal(object)
    gatewayError = Signal(str)

    def __init__(self, port=8765, parent=None):
        super().__init__(parent)
        self.port = port
        self.server = QWebSocketServer("VirtualLab Instrument Gateway", QWebSocketServer.NonSecureMode, self)
        self.server.newConnection.connect(self._on_new_connection)
        
        self.registry = ConnectionRegistry()
        
        # Legacy lists, maintained for compatibility but registry is source of truth
        self.sensor_clients = []
        self.camera_clients = []
        self.control_clients = []
        
        self.decoder = PacketDecoder()
        self.camera_decoder = CameraFrameDecoder()
        self.control_decoder = ControlMessageDecoder()
        
        self.active_session_id = "PREVIEW"
        self.camera_binary_messages_received = 0
        self.camera_bytes_received = 0

    def start(self) -> bool:
        from PySide6.QtNetwork import QHostAddress
        if self.server.listen(QHostAddress.Any, self.port):
            logger.info("[GATEWAY] Started on port %d", self.port)
            return True
        else:
            self.gatewayError.emit(f"Failed to start server on port {self.port}")
            return False

    def stop(self):
        for conn in list(self.registry.connections.values()):
            if conn.socket:
                conn.socket.close()
        self.server.close()
        logger.info("[GATEWAY] Stopped")

    def set_active_session(self, session_id: str):
        self.active_session_id = session_id

    def _on_new_connection(self):
        client_socket = self.server.nextPendingConnection()
        
        path = client_socket.requestUrl().path()
        if path not in ["/sensors", "/camera", "/control"]:
            logger.warning("[GATEWAY] Rejected unknown path: %s", path)
            client_socket.close()
            client_socket.deleteLater()
            return
            
        c_type = path.strip("/")
        conn_id = generate_id("CONN")
        remote_ip = client_socket.peerAddress().toString()
        
        conn_state = ChannelConnectionState(
            channel_type=c_type,
            connection_id=conn_id,
            generation=1,
            socket=client_socket,
            remote_address=remote_ip,
            connected_utc=int(time.time()*1000)
        )
        self.registry.add_connection(conn_state)
        
        logger.info("[%s] accepted path=%s channel=%s", conn_id, path, c_type.upper())
        self.channelConnected.emit(path, conn_id)
        
        if path == "/sensors":
            self.sensor_clients.append(client_socket)
            client_socket.textMessageReceived.connect(lambda msg, s=client_socket, cid=conn_id: self._on_message(s, cid, msg))
        elif path == "/camera":
            self.camera_clients.append(client_socket)
            client_socket.textMessageReceived.connect(lambda msg, s=client_socket, cid=conn_id: self._on_camera_text_message(s, cid, msg))
            client_socket.binaryMessageReceived.connect(lambda msg, s=client_socket, cid=conn_id: self._on_binary_message(s, cid, msg))
        elif path == "/control":
            self.control_clients.append(client_socket)
            client_socket.textMessageReceived.connect(lambda msg, s=client_socket, cid=conn_id: self._on_control_message(s, cid, msg))
            
        client_socket.disconnected.connect(lambda s=client_socket, p=path, cid=conn_id: self._on_disconnect(s, p, cid))

    def _handle_late_binding(self, path: str, conn_id: str, device_id: str):
        conn = self.registry.get_connection(conn_id)
        if not conn: return
        
        if conn.bound_device_id is None:
            c_type = path.strip("/").upper()
            logger.info("[%s][%s] late binding to %s", c_type, conn_id, device_id)
            try:
                self.registry.bind_connection(conn_id, device_id)
                self.channelBound.emit(path, conn_id, device_id)
                
                # Projection logic
                dev_state = self.registry.devices.get(device_id)
                if dev_state and len([c for c in [dev_state.sensors, dev_state.camera, dev_state.control] if c and c.state.value != "DISCONNECTED"]) == 1:
                    # First channel to bind triggers the global connect
                    self.instrumentConnected.emit(device_id, conn.remote_address)
            except ValueError as e:
                logger.error("[%s][%s] immutable binding error: %s", c_type, conn_id, e)
                conn.socket.close()

    def _try_parse_hello(self, path: str, conn_id: str, raw: str) -> bool:
        try:
            data = json.loads(raw)
            if data.get("message_type") == "CHANNEL_HELLO":
                dev_id = data.get("device_id")
                hello_channel = data.get("channel")
                expected_channel = path.strip("/")
                if hello_channel and hello_channel != expected_channel:
                    logger.error("[%s] protocol mismatch: hello channel '%s' does not match path '%s'", conn_id, hello_channel, path)
                    return True
                if dev_id and dev_id != "UNKNOWN":
                    self._handle_late_binding(path, conn_id, dev_id)
                return True
        except Exception:
            pass
        return False

    def _on_message(self, socket, conn_id, raw: str):
        conn = self.registry.get_connection(conn_id)
        if conn:
            conn.last_activity_utc = int(time.time()*1000)
            conn.message_count += 1
            if conn.channel_type != "sensors":
                logger.error("[%s][%s] protocol mismatch: text message on non-sensors channel", conn_id, conn.channel_type.upper())
                return
            
        if self._try_parse_hello("/sensors", conn_id, raw):
            return
            
        try:
            measurement = self.decoder.decode(raw, self.active_session_id)
            if not measurement.instrument_id or measurement.instrument_id == "UNKNOWN":
                logger.warning("[%s][SENSORS] DEVICE_ID MISSING - CHANNEL UNBOUND", conn_id)
            else:
                logger.debug("[%s][SENSORS] Measurement decoded", conn_id)
                self._handle_late_binding("/sensors", conn_id, measurement.instrument_id)
                if conn and conn.state != SensorChannelState.STREAMING:
                    conn.state = SensorChannelState.STREAMING
                    dev_id = conn.bound_device_id or "UNBOUND"
                    logger.info("[%s][SENSORS] STREAMING", dev_id)
        except Exception as exc:
            if conn:
                conn.last_error = str(exc)
                conn.state = SensorChannelState.FAILED
            self.gatewayError.emit(str(exc))
            return
            
        self.measurementReceived.emit(measurement)
        
    def _on_camera_text_message(self, socket, conn_id, raw: str):
        conn = self.registry.get_connection(conn_id)
        if conn:
            conn.last_activity_utc = int(time.time()*1000)
            conn.message_count += 1
            
        self._try_parse_hello("/camera", conn_id, raw)

    def _on_binary_message(self, socket, conn_id, raw_bytes: bytes):
        conn = self.registry.get_connection(conn_id)
        if hasattr(raw_bytes, 'data'):
            raw_bytes = raw_bytes.data()
            
        if conn:
            conn.last_activity_utc = int(time.time()*1000)
            conn.message_count += 1
            conn.byte_count += len(raw_bytes)
            if conn.channel_type != "camera":
                logger.error("[%s][%s] protocol mismatch: binary frame on non-camera channel", conn_id, conn.channel_type.upper())
                return
                
        self.camera_binary_messages_received += 1
        self.camera_bytes_received += len(raw_bytes)
        
        try:
            frame = self.camera_decoder.decode(raw_bytes)
            logger.debug("[%s][CAMERA] CameraFrame decoded seq=%s", conn_id, frame.frame_sequence)
            self._handle_late_binding("/camera", conn_id, frame.device_id)
            if conn and conn.state != CameraChannelState.STREAMING:
                conn.state = CameraChannelState.STREAMING
                dev_id = conn.bound_device_id or "UNBOUND"
                logger.info("[%s][CAMERA] STREAMING", dev_id)
        except Exception as exc:
            if conn:
                conn.last_error = str(exc)
                conn.state = CameraChannelState.FAILED
            self.gatewayError.emit(str(exc))
            return
            
        self.binaryMessageReceived.emit(frame)

    def _on_control_message(self, socket, conn_id, raw: str):
        conn = self.registry.get_connection(conn_id)
        if conn:
            conn.last_activity_utc = int(time.time()*1000)
            conn.message_count += 1
            if conn.channel_type != "control":
                logger.error("[%s][%s] protocol mismatch: text message on non-control channel", conn_id, conn.channel_type.upper())
                return
            
        if self._try_parse_hello("/control", conn_id, raw):
            return
            
        try:
            result = self.control_decoder.decode(raw)
        except Exception as exc:
            if conn:
                conn.last_error = str(exc)
                conn.state = ControlChannelState.FAILED
            self.gatewayError.emit(f"Control Parse Error: {str(exc)}")
            return
            
        if result["type"] == "CAPABILITIES":
            dev_id = result["capabilities"].camera_stream_key.device_id
            self._handle_late_binding("/control", conn_id, dev_id)
            self.controlCapabilityReceived.emit(result["capabilities"])
        elif result["type"] == "RESPONSE":
            self.controlMessageReceived.emit(result)

    def _on_disconnect(self, socket, path, conn_id):
        c_type = path.strip("/").upper()
        
        conn = self.registry.get_connection(conn_id)
        dev_id = conn.bound_device_id if conn else "UNBOUND"
        logger.info("[%s][%s][%s] disconnected", c_type, dev_id, conn_id)
        
        self.channelDisconnected.emit(path, conn_id)
        self.registry.remove_connection(conn_id)
        
        if path == "/sensors" and socket in self.sensor_clients:
            self.sensor_clients.remove(socket)
        elif path == "/camera" and socket in self.camera_clients:
            self.camera_clients.remove(socket)
        elif path == "/control" and socket in self.control_clients:
            self.control_clients.remove(socket)
            
        socket.deleteLater()
        
        if dev_id != "UNBOUND":
            dev_state = self.registry.devices.get(dev_id)
            if dev_state:
                # If all channels are disconnected, project a global disconnect
                if dev_state.overall_state().value == "DISCONNECTED":
                    self.instrumentDisconnected.emit(dev_id)

    def send_control_message(self, msg: dict, device_id: str = None):
        if not device_id:
            # Fallback for legacy
            if not self.control_clients:
                self.gatewayError.emit("CONTROL CHANNEL DISCONNECTED")
                return
            raw = json.dumps(msg)
            for client in self.control_clients:
                client.sendTextMessage(raw)
        else:
            dev = self.registry.devices.get(device_id)
            if dev and dev.control and dev.control.socket:
                dev.control.socket.sendTextMessage(json.dumps(msg))
            else:
                self.gatewayError.emit(f"CONTROL CHANNEL DISCONNECTED FOR {device_id}")
