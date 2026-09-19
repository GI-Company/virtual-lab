import json
import pytest
import subprocess
import os
from virtual_lab.core.canonical import canonical_json

import json
import pytest
import subprocess
import os
import jsonschema
from virtual_lab.core.canonical import canonical_json

SCHEMA = {
    "type": "object",
    "properties": {
        "protocol_version": {"type": "string"},
        "message_type": {"type": "string"},
        "stream_id": {"type": "string"},
        "device_id": {"type": "string"},
        "device_timebase": {"type": "integer"},
        "sequence": {"type": "integer"},
        "sensor": {"type": "string"},
        "measurement_type": {"type": "string"},
        "values": {
            "type": "object",
            "additionalProperties": {"type": "number"}
        },
        "units": {
            "type": "object",
            "additionalProperties": {"type": "string"}
        },
        "accuracy": {"type": "integer"},
        "acquisition_metadata": {
            "type": "object",
            "properties": {"exposure_ms": {"type": "integer"}},
            "required": ["exposure_ms"]
        },
        "camera_metadata": {
            "type": "object",
            "properties": {"gain": {"type": "number"}},
            "required": ["gain"]
        }
    },
    "required": [
        "protocol_version", "message_type", "stream_id", "device_id",
        "device_timebase", "sequence", "sensor", "measurement_type",
        "values", "units", "accuracy", "acquisition_metadata", "camera_metadata"
    ]
}

def test_python_kotlin_canonical_interop():
    # Construct a sample measurement packet
    payload = {
        "protocol_version": "1.0",
        "message_type": "measurement",
        "stream_id": "STREAM-123",
        "device_id": "DEVICE-456",
        "device_timebase": 1234567890,
        "sequence": 42,
        "sensor": "CMOS",
        "measurement_type": "fluorescence",
        "values": {"channel1": 1.23, "channel2": 4.56},
        "units": {"channel1": "RFU", "channel2": "RFU"},
        "accuracy": 95,
        "acquisition_metadata": {"exposure_ms": 10},
        "camera_metadata": {"gain": 2.0}
    }

    # Python canonicalization
    py_canonical = canonical_json(payload)
    
    # Execute Kotlin program to generate JSON
    interop_dir = os.path.join(os.path.dirname(__file__), "kotlin_interop")
    env = os.environ.copy()
    env["JAVA_HOME"] = "/opt/homebrew/opt/openjdk@21"
    result = subprocess.run(["gradle", "run", "--no-daemon", "--quiet"], cwd=interop_dir, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        pytest.fail(f"Kotlin execution failed: {result.stderr}")
        
    kt_json_str = result.stdout.strip()
    kt_parsed = json.loads(kt_json_str)
    
    # Validate Kotlin output against JSON Schema
    jsonschema.validate(instance=kt_parsed, schema=SCHEMA)
    
    # Canonicalize Kotlin JSON
    kt_canonical = canonical_json(kt_parsed)
    
    # Python deserialize Kotlin's canonical JSON
    py_deserialized_kt = json.loads(kt_canonical.decode('utf-8'))
    
    # Compare byte equality of canonical outputs
    assert py_canonical == kt_canonical
    assert payload == py_deserialized_kt


def test_python_kotlin_python_bidirectional_interop():
    payload = {
        "protocol_version": "1.0",
        "message_type": "measurement",
        "stream_id": "STREAM-999",
        "device_id": "DEVICE-888",
        "device_timebase": 9876543210,
        "sequence": 100,
        "sensor": "IMU",
        "measurement_type": "acceleration",
        "values": {"x": 0.1, "y": 0.2, "z": 9.8},
        "units": {"x": "m/s^2", "y": "m/s^2", "z": "m/s^2"},
        "accuracy": 99,
        "acquisition_metadata": {"exposure_ms": 5},
        "camera_metadata": {"gain": 1.0}
    }
    
    # 1. Python canonicalization
    py_canonical = canonical_json(payload)
    py_json_str = json.dumps(payload)
    
    # 2. Pass to Kotlin
    interop_dir = os.path.join(os.path.dirname(__file__), "kotlin_interop")
    env = os.environ.copy()
    env["JAVA_HOME"] = "/opt/homebrew/opt/openjdk@21"
    # Wrap in single quotes so gradle treats it as one argument and preserves double quotes
    gradle_args = f"--args='{py_json_str}'"
    result = subprocess.run(["gradle", "run", gradle_args, "--no-daemon", "--quiet"], cwd=interop_dir, capture_output=True, text=True, env=env)
    
    if result.returncode != 0:
        pytest.fail(f"Kotlin execution failed: {result.stderr}")
        
    kt_json_str = result.stdout.strip()
    kt_parsed = json.loads(kt_json_str)
    
    # 3. Validate Kotlin output
    jsonschema.validate(instance=kt_parsed, schema=SCHEMA)
    kt_canonical = canonical_json(kt_parsed)
    
    # 4. Compare byte equality
    assert py_canonical == kt_canonical
    assert payload == json.loads(kt_canonical.decode('utf-8'))


