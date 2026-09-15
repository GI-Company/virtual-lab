import pytest
import time
import json
import logging
from unittest.mock import Mock, patch
from virtual_lab.instruments.transport.gateway import InstrumentGateway
from virtual_lab.instruments.connection import SensorChannelState, CameraChannelState, ControlChannelState
from PySide6.QtWebSockets import QWebSocket

class MockSocket:
    def __init__(self, path="/sensors"):
        self._path = path
        self.textMessageReceived = Mock()
        self.binaryMessageReceived = Mock()
        self.disconnected = Mock()
    def requestUrl(self):
        url = Mock()
        url.path.return_value = self._path
        return url
    def peerAddress(self):
        addr = Mock()
        addr.toString.return_value = "127.0.0.1"
        return addr
    def close(self):
        pass
    def deleteLater(self):
        pass

def test_three_sockets_unique_ids():
    with patch("virtual_lab.instruments.transport.gateway.QWebSocketServer") as mock_server:
        gw = InstrumentGateway(8765)
        
        s1 = MockSocket("/sensors")
        s2 = MockSocket("/camera")
        s3 = MockSocket("/control")
        
        gw.server.nextPendingConnection.side_effect = [s1, s2, s3]
        
        gw._on_new_connection()
        gw._on_new_connection()
        gw._on_new_connection()
        
        conn_ids = set()
        for client in gw.registry.connections.values():
            conn_ids.add(client.connection_id)
            
        assert len(conn_ids) == 3

def test_sensor_measurement_binds_and_streams():
    with patch("virtual_lab.instruments.transport.gateway.QWebSocketServer") as mock_server:
        gw = InstrumentGateway(8765)
        s1 = MockSocket("/sensors")
        gw.server.nextPendingConnection.return_value = s1
        gw._on_new_connection()
        conn_id = list(gw.registry.connections.keys())[0]
        
        raw_measurement = json.dumps({
            "schema_version": "1",
            "message_type": "MEASUREMENT",
            "device_id": "ANDROID-test",
            "session_id": "S1",
            "sequence_number": 1,
            "timestamp_utc": 1000,
            "measurement_type": "ACCELERATION",
            "values": {"ax": 0.0, "ay": 0.0, "az": 1.0},
            "units": {"ax": "m/s^2", "ay": "m/s^2", "az": "m/s^2"}
        })
        
        gw._on_message(s1, conn_id, raw_measurement)
        
        conn = gw.registry.get_connection(conn_id)
        if conn.last_error:
            print(f"DECODER ERROR: {conn.last_error}")
            
        dev = gw.registry.devices.get("ANDROID-test")
        assert dev is not None
        assert dev.sensors.state == SensorChannelState.STREAMING

def test_channel_hello_binds_idle_camera():
    with patch("virtual_lab.instruments.transport.gateway.QWebSocketServer") as mock_server:
        gw = InstrumentGateway(8765)
        s1 = MockSocket("/camera")
        gw.server.nextPendingConnection.return_value = s1
        gw._on_new_connection()
        conn_id = list(gw.registry.connections.keys())[0]
        
        hello = json.dumps({
            "schema_version": "1",
            "message_type": "CHANNEL_HELLO",
            "device_id": "ANDROID-c0f8e767",
            "channel": "camera"
        })
        gw._on_camera_text_message(s1, conn_id, hello)
        
        dev = gw.registry.devices.get("ANDROID-c0f8e767")
        assert dev is not None
        assert dev.camera.state == CameraChannelState.CONNECTED

def test_hello_channel_must_match_url_path():
    with patch("virtual_lab.instruments.transport.gateway.QWebSocketServer") as mock_server:
        gw = InstrumentGateway(8765)
        s1 = MockSocket("/camera")
        gw.server.nextPendingConnection.return_value = s1
        gw._on_new_connection()
        conn_id = list(gw.registry.connections.keys())[0]
        
        hello = json.dumps({
            "schema_version": "1",
            "message_type": "CHANNEL_HELLO",
            "device_id": "ANDROID-c0f8e767",
            "channel": "sensors"
        })
        gw._on_camera_text_message(s1, conn_id, hello)
        
        # Should be rejected
        dev = gw.registry.devices.get("ANDROID-c0f8e767")
        assert dev is None

def test_info_logging_occurs_on_transition(caplog):
    with patch("virtual_lab.instruments.transport.gateway.QWebSocketServer") as mock_server:
        gw = InstrumentGateway(8765)
        s1 = MockSocket("/sensors")
        gw.server.nextPendingConnection.return_value = s1
        gw._on_new_connection()
        conn_id = list(gw.registry.connections.keys())[0]
        
        raw_measurement = json.dumps({
            "schema_version": "1",
            "message_type": "MEASUREMENT",
            "device_id": "ANDROID-test",
            "session_id": "S1",
            "sequence_number": 1,
            "timestamp_utc": 1000,
            "measurement_type": "ACCELERATION",
            "values": {"ax": 0.0, "ay": 0.0, "az": 1.0},
            "units": {"ax": "m/s^2", "ay": "m/s^2", "az": "m/s^2"}
        })
        
        with caplog.at_level(logging.INFO):
            gw._on_message(s1, conn_id, raw_measurement)
            gw._on_message(s1, conn_id, raw_measurement)
            gw._on_message(s1, conn_id, raw_measurement)
        
        # STREAMING should only be logged once
        streaming_logs = [r for r in caplog.records if "STREAMING" in r.message]
        assert len(streaming_logs) == 1
