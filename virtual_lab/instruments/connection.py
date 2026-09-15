from enum import Enum
import time
from typing import Optional, Dict
from dataclasses import dataclass, field
from PySide6.QtWebSockets import QWebSocket

class SensorChannelState(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    STREAMING = "STREAMING"
    FAILED = "FAILED"

class CameraChannelState(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    IDLE = "IDLE"
    STREAMING = "STREAMING"
    FAILED = "FAILED"

class ControlChannelState(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    READY = "READY"
    BUSY = "BUSY"
    FAILED = "FAILED"

class InstrumentState(Enum):
    DISCONNECTED = "DISCONNECTED"
    PARTIAL = "PARTIAL"
    READY = "READY"
    ACQUIRING = "ACQUIRING"
    DEGRADED = "DEGRADED"

@dataclass
class ChannelConnectionState:
    channel_type: str  # "sensors", "camera", "control"
    connection_id: str
    generation: int
    socket: QWebSocket
    remote_address: str
    connected_utc: int
    bound_device_id: Optional[str] = None
    state: Enum = None
    last_activity_utc: Optional[int] = None
    message_count: int = 0
    byte_count: int = 0
    last_error: Optional[str] = None
    
    def __post_init__(self):
        if self.state is None:
            if self.channel_type == "sensors":
                self.state = SensorChannelState.CONNECTED
            elif self.channel_type == "camera":
                self.state = CameraChannelState.CONNECTED
            elif self.channel_type == "control":
                self.state = ControlChannelState.CONNECTED

@dataclass
class DeviceConnectionState:
    device_id: str
    sensors: Optional[ChannelConnectionState] = None
    camera: Optional[ChannelConnectionState] = None
    control: Optional[ChannelConnectionState] = None
    
    def overall_state(self) -> InstrumentState:
        s_ok = self.sensors is not None and self.sensors.state not in (SensorChannelState.DISCONNECTED, SensorChannelState.FAILED)
        c_ok = self.camera is not None and self.camera.state not in (CameraChannelState.DISCONNECTED, CameraChannelState.FAILED)
        ctl_ok = self.control is not None and self.control.state not in (ControlChannelState.DISCONNECTED, ControlChannelState.FAILED)
        
        has_any = s_ok or c_ok or ctl_ok
        has_all = s_ok and c_ok and ctl_ok
        
        if not has_any:
            return InstrumentState.DISCONNECTED
            
        # Determine if acquiring
        acquiring = False
        if self.sensors and self.sensors.state == SensorChannelState.STREAMING:
            acquiring = True
        if self.camera and self.camera.state == CameraChannelState.STREAMING:
            acquiring = True
            
        if has_all:
            # Check for DEGRADED (if something failed)
            if (self.sensors and self.sensors.state == SensorChannelState.FAILED) or \
               (self.camera and self.camera.state == CameraChannelState.FAILED) or \
               (self.control and self.control.state == ControlChannelState.FAILED):
                return InstrumentState.DEGRADED
                
            if acquiring:
                return InstrumentState.ACQUIRING
            return InstrumentState.READY
            
        # Not all connected, but some are
        if (self.sensors and self.sensors.state == SensorChannelState.FAILED) or \
           (self.camera and self.camera.state == CameraChannelState.FAILED) or \
           (self.control and self.control.state == ControlChannelState.FAILED):
            return InstrumentState.DEGRADED
            
        return InstrumentState.PARTIAL

class ConnectionRegistry:
    def __init__(self):
        # device_id -> DeviceConnectionState
        self.devices: Dict[str, DeviceConnectionState] = {}
        # connection_id -> ChannelConnectionState
        self.connections: Dict[str, ChannelConnectionState] = {}
        
    def add_connection(self, conn_state: ChannelConnectionState):
        self.connections[conn_state.connection_id] = conn_state
        
    def get_connection(self, connection_id: str) -> Optional[ChannelConnectionState]:
        return self.connections.get(connection_id)
        
    def bind_connection(self, connection_id: str, device_id: str):
        conn = self.connections.get(connection_id)
        if not conn:
            raise ValueError(f"Connection {connection_id} not found")
            
        if conn.bound_device_id is not None:
            if conn.bound_device_id != device_id:
                raise ValueError(f"Socket immutable binding mismatch. Expected {conn.bound_device_id}, got {device_id}")
            return # Already bound to this device
            
        conn.bound_device_id = device_id
        
        if device_id not in self.devices:
            self.devices[device_id] = DeviceConnectionState(device_id=device_id)
            
        device = self.devices[device_id]
        ctype = conn.channel_type
        
        # Check for duplicate replacement
        old_conn = None
        if ctype == "sensors":
            old_conn = device.sensors
            device.sensors = conn
        elif ctype == "camera":
            old_conn = device.camera
            device.camera = conn
        elif ctype == "control":
            old_conn = device.control
            device.control = conn
            
        if old_conn and old_conn.connection_id != connection_id:
            # Supersede old connection
            conn.generation = old_conn.generation + 1
            if old_conn.socket:
                try:
                    old_conn.socket.close()
                except Exception:
                    pass
        else:
            conn.generation = 1
            
    def remove_connection(self, connection_id: str):
        conn = self.connections.pop(connection_id, None)
        if not conn:
            return
            
        if conn.bound_device_id and conn.bound_device_id in self.devices:
            device = self.devices[conn.bound_device_id]
            ctype = conn.channel_type
            
            # Only clear the device channel if the generation/connection_id matches
            if ctype == "sensors" and device.sensors and device.sensors.connection_id == connection_id:
                device.sensors.state = SensorChannelState.DISCONNECTED
            elif ctype == "camera" and device.camera and device.camera.connection_id == connection_id:
                device.camera.state = CameraChannelState.DISCONNECTED
            elif ctype == "control" and device.control and device.control.connection_id == connection_id:
                device.control.state = ControlChannelState.DISCONNECTED
