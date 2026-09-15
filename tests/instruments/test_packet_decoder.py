import pytest
import json
from virtual_lab.instruments.transport.packet_parser import PacketDecoder

def test_legacy_magnetometer():
    decoder = PacketDecoder()
    raw = json.dumps({
        "device_id": "MOCK-1",
        "values": {"x_ut": 10.0, "y_ut": 20.0, "z_ut": 30.0},
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
        "device_id": "MOCK-1",
        "measurement_type": "ACCELERATION",
        "values": {"ax": 1.0, "ay": 2.0, "az": 9.8},
        "units": {"ax": "m/s^2", "ay": "m/s^2", "az": "m/s^2"}
    })
    m = decoder.decode(raw, "SES-1")
    assert m.quantity == "ACCELERATION"
    assert m.values["az"] == 9.8
    assert decoder.total_decoded == 1

def test_unknown_type_rejected():
    decoder = PacketDecoder()
    raw = json.dumps({
        "measurement_type": "GRAVITY",
        "values": {"x": 1.0},
        "units": {"x": "m/s^2"}
    })
    with pytest.raises(ValueError, match="Unsupported measurement_type"):
        decoder.decode(raw, "SES-1")
    assert decoder.total_rejected == 1

def test_incorrect_units_rejected():
    decoder = PacketDecoder()
    raw = json.dumps({
        "measurement_type": "PRESSURE",
        "values": {"pressure": 1000.0},
        "units": {"pressure": "uT"}
    })
    with pytest.raises(ValueError, match="Unit mismatch"):
        decoder.decode(raw, "SES-1")
    assert decoder.total_rejected == 1

def test_interleaved_sequences():
    decoder = PacketDecoder()
    
    raw_mag1 = json.dumps({
        "device_id": "MOCK-1",
        "sensor_id": "mag",
        "measurement_type": "MAGNETIC_FIELD",
        "values": {"bx": 1.0, "by": 0, "bz": 0},
        "units": {"bx": "uT", "by": "uT", "bz": "uT"},
        "sequence": 1
    })
    
    raw_acc1 = json.dumps({
        "device_id": "MOCK-1",
        "sensor_id": "acc",
        "measurement_type": "ACCELERATION",
        "values": {"ax": 1.0, "ay": 0, "az": 0},
        "units": {"ax": "m/s^2", "ay": "m/s^2", "az": "m/s^2"},
        "sequence": 1
    })
    
    raw_mag2 = json.dumps({
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
    
    key_mag = ("MOCK-1", "mag", "MAGNETIC_FIELD")
    key_acc = ("MOCK-1", "acc", "ACCELERATION")
    
    assert decoder.seq_counters[key_mag] == 2
    assert decoder.seq_counters[key_acc] == 1
