import pytest
from virtual_lab.instruments.connection import ConnectionRegistry, ChannelConnectionState, SensorChannelState, CameraChannelState, ControlChannelState

class MockSocket:
    def __init__(self):
        self.closed = False
    def close(self):
        self.closed = True

def test_immutable_binding():
    registry = ConnectionRegistry()
    conn1 = ChannelConnectionState("sensors", "CONN-1", 1, MockSocket(), "192.168.1.1", 1000)
    registry.add_connection(conn1)
    
    registry.bind_connection("CONN-1", "ANDROID-1")
    assert conn1.bound_device_id == "ANDROID-1"
    
    # Attempting to bind same device is fine
    registry.bind_connection("CONN-1", "ANDROID-1")
    
    # Attempting to bind different device should fail
    with pytest.raises(ValueError, match="Socket immutable binding mismatch"):
        registry.bind_connection("CONN-1", "ANDROID-2")

def test_duplicate_channel_superseding():
    registry = ConnectionRegistry()
    s1 = MockSocket()
    conn1 = ChannelConnectionState("sensors", "CONN-1", 1, s1, "192.168.1.1", 1000)
    registry.add_connection(conn1)
    registry.bind_connection("CONN-1", "ANDROID-1")
    
    assert registry.devices["ANDROID-1"].sensors.connection_id == "CONN-1"
    assert registry.devices["ANDROID-1"].sensors.generation == 1
    
    # New socket connects for same device/channel
    s2 = MockSocket()
    conn2 = ChannelConnectionState("sensors", "CONN-2", 1, s2, "192.168.1.1", 2000)
    registry.add_connection(conn2)
    registry.bind_connection("CONN-2", "ANDROID-1")
    
    # Old socket should be closed, new one takes over, generation increments
    assert s1.closed == True
    assert registry.devices["ANDROID-1"].sensors.connection_id == "CONN-2"
    assert registry.devices["ANDROID-1"].sensors.generation == 2

def test_stale_disconnect_handling():
    registry = ConnectionRegistry()
    s1 = MockSocket()
    conn1 = ChannelConnectionState("camera", "CONN-1", 1, s1, "192.168.1.1", 1000)
    registry.add_connection(conn1)
    registry.bind_connection("CONN-1", "ANDROID-1")
    
    # New connection supersedes it
    s2 = MockSocket()
    conn2 = ChannelConnectionState("camera", "CONN-2", 1, s2, "192.168.1.1", 2000)
    registry.add_connection(conn2)
    registry.bind_connection("CONN-2", "ANDROID-1")
    
    # Now the stale disconnect for CONN-1 arrives
    registry.remove_connection("CONN-1")
    
    # CONN-2 should remain active
    dev = registry.devices["ANDROID-1"]
    assert dev.camera.connection_id == "CONN-2"
    assert dev.camera.state != CameraChannelState.DISCONNECTED

def test_device_overall_state():
    registry = ConnectionRegistry()
    
    # Add sensors
    conn_s = ChannelConnectionState("sensors", "CONN-S", 1, MockSocket(), "IP", 1000)
    registry.add_connection(conn_s)
    registry.bind_connection("CONN-S", "ANDROID-1")
    
    dev = registry.devices["ANDROID-1"]
    assert dev.overall_state().value == "PARTIAL"
    
    # Add control
    conn_ctl = ChannelConnectionState("control", "CONN-C", 1, MockSocket(), "IP", 1000)
    registry.add_connection(conn_ctl)
    registry.bind_connection("CONN-C", "ANDROID-1")
    assert dev.overall_state().value == "PARTIAL"
    
    # Add camera
    conn_cam = ChannelConnectionState("camera", "CONN-CAM", 1, MockSocket(), "IP", 1000)
    registry.add_connection(conn_cam)
    registry.bind_connection("CONN-CAM", "ANDROID-1")
    
    assert dev.overall_state().value == "READY"
    
    # Set camera streaming
    dev.camera.state = CameraChannelState.STREAMING
    assert dev.overall_state().value == "ACQUIRING"
    
    # Simulate a channel failure
    dev.sensors.state = SensorChannelState.FAILED
    assert dev.overall_state().value == "DEGRADED"

    # Fully disconnect
    registry.remove_connection("CONN-S")
    registry.remove_connection("CONN-C")
    registry.remove_connection("CONN-CAM")
    assert dev.overall_state().value == "DISCONNECTED"
