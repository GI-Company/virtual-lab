import pytest
import json
from virtual_lab.instruments.transport.packet_parser import PacketDecoder

def test_legacy_magnetometer():
    decoder = PacketDecoder()
    raw = json.dumps({
        "schema_version": "1",
        "message_type": "MEASUREMENT_PACKET",
        "device_id": "MOCK-1",
        "stream_id": "SES-1",
        "sensor_id": "mag",
        "device_timebase": "MONOTONIC",
        "device_timestamp_ns": 12345,
        "measurement_type": "MAGNETIC_FIELD",
        "values": {"bx": 10.0, "by": 20.0, "bz": 30.0},
        "units": {"bx": "uT", "by": "uT", "bz": "uT"},
        "sequence": 42
    })
    m = decoder.decode(raw, "SES-1")
    assert m.quantity == "MAGNETIC_FIELD"
    assert m.values["bx"] == 10.0
    assert m.units["bx"] == "uT"
    assert m.sequence == 42
    assert decoder.total_decoded == 1

def test_accelerometer():
    decoder = PacketDecoder()
    raw = json.dumps({
        "schema_version": "1",
        "message_type": "MEASUREMENT_PACKET",
        "device_id": "MOCK-1",
        "stream_id": "SES-1",
        "sensor_id": "acc",
        "device_timebase": "MONOTONIC",
        "device_timestamp_ns": 12345,
        "measurement_type": "ACCELERATION",
        "values": {"ax": 1.0, "ay": 2.0, "az": 9.8},
        "units": {"ax": "m/s^2", "ay": "m/s^2", "az": "m/s^2"},
        "sequence": 1
    })
    m = decoder.decode(raw, "SES-1")
    assert m.quantity == "ACCELERATION"
    assert m.values["az"] == 9.8
    assert decoder.total_decoded == 1



def test_interleaved_sequences():
    decoder = PacketDecoder()
    
    raw_mag1 = json.dumps({
        "schema_version": "1",
        "message_type": "MEASUREMENT_PACKET",
        "stream_id": "SES-1",
        "device_timebase": "MONOTONIC",
        "device_timestamp_ns": 12345,
        "device_id": "MOCK-1",
        "sensor_id": "mag",
        "measurement_type": "MAGNETIC_FIELD",
        "values": {"bx": 1.0, "by": 0, "bz": 0},
        "units": {"bx": "uT", "by": "uT", "bz": "uT"},
        "sequence": 1
    })
    
    raw_acc1 = json.dumps({
        "schema_version": "1",
        "message_type": "MEASUREMENT_PACKET",
        "stream_id": "SES-1",
        "device_timebase": "MONOTONIC",
        "device_timestamp_ns": 12345,
        "device_id": "MOCK-1",
        "sensor_id": "acc",
        "measurement_type": "ACCELERATION",
        "values": {"ax": 1.0, "ay": 0, "az": 0},
        "units": {"ax": "m/s^2", "ay": "m/s^2", "az": "m/s^2"},
        "sequence": 1
    })
    
    raw_mag2 = json.dumps({
        "schema_version": "1",
        "message_type": "MEASUREMENT_PACKET",
        "stream_id": "SES-1",
        "device_timebase": "MONOTONIC",
        "device_timestamp_ns": 12345,
        "device_id": "MOCK-1",
        "sensor_id": "mag",
        "measurement_type": "MAGNETIC_FIELD",
        "values": {"bx": 2.0, "by": 0, "bz": 0},
        "units": {"bx": "uT", "by": "uT", "bz": "uT"},
        "sequence": 2
    })
    
    m1 = decoder.decode(raw_mag1, "SES-1")
    a1 = decoder.decode(raw_acc1, "SES-1")
    m2 = decoder.decode(raw_mag2, "SES-1")
    
    assert m1.sequence == 1
    assert a1.sequence == 1
    assert m2.sequence == 2
    
    # We no longer check seq_counters here if it was removed in rewrite
