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

def test_sensors_only_partial_connection():
    registry = ConnectionRegistry()
    
    # Simulate a local adb reverse connection
    s = MockSocket()
    conn_s = ChannelConnectionState("sensors", "CONN-S1", 1, s, "127.0.0.1", 1000)
    registry.add_connection(conn_s)
    
    # Bind to persistent device_id from measurement
    registry.bind_connection("CONN-S1", "ANDROID-test123")
    
    # Assert registry state
    dev = registry.devices["ANDROID-test123"]
    
    assert dev.sensors is not None
    assert dev.sensors.state == SensorChannelState.CONNECTED
    
    assert dev.camera is None
    assert dev.control is None
    
    # Overall state must be PARTIAL (or ACQUIRING if streaming), NOT DISCONNECTED
    assert dev.overall_state().value == "PARTIAL"
    
    # If it starts streaming, it should be ACQUIRING
    dev.sensors.state = SensorChannelState.STREAMING
    assert dev.overall_state().value == "ACQUIRING"

def test_live_recording_channel_attribution_bug():
    registry = ConnectionRegistry()
    
    # 1. /sensors connection
    conn_s = ChannelConnectionState("sensors", "CONN-S1", 1, MockSocket(), "192.168.1.5", 1000)
    registry.add_connection(conn_s)
    registry.bind_connection("CONN-S1", "ANDROID-c0f8e767")
    conn_s.state = SensorChannelState.STREAMING
    
    # 2. /camera connection
    conn_c = ChannelConnectionState("camera", "CONN-C1", 1, MockSocket(), "192.168.1.5", 1000)
    registry.add_connection(conn_c)
    registry.bind_connection("CONN-C1", "ANDROID-c0f8e767")
    # Camera has 0 valid frames, remains CONNECTED (which means IDLE)
    
    # 3. /control absent
    
    dev = registry.devices["ANDROID-c0f8e767"]
    
    assert dev.sensors.state == SensorChannelState.STREAMING
    assert dev.camera.state == CameraChannelState.CONNECTED
    assert dev.control is None
    
    assert dev.overall_state().value == "ACQUIRING"
    
    # Then disconnect /sensors
    registry.remove_connection("CONN-S1")
    
    assert dev.sensors.state == SensorChannelState.DISCONNECTED
    assert dev.camera.state == CameraChannelState.CONNECTED
    assert dev.overall_state().value == "PARTIAL"
