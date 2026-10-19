import os
import json
import hashlib
from collections import defaultdict
from typing import Protocol, Optional
from datetime import datetime, timezone
from dataclasses import asdict

from virtual_lab.instruments.measurements import Measurement

class MeasurementStore(Protocol):
    def begin(self, session_id: str, instrument_id: str, metadata: dict): ...
    def append(self, measurement: Measurement): ...
    def commit(self, dropped_counts: dict=None, rejected_count: int=0) -> dict: ...
    def abort(self, reason: str): ...

class JsonlMeasurementStore:
    def __init__(self, base_dir: Optional[str] = None):
        from virtual_lab.core.paths import app_data_dir
        self.base_dir = str(base_dir) if base_dir is not None else str(app_data_dir() / "instruments")
        self.session_id: Optional[str] = None
        self.instrument_id: Optional[str] = None
        self.session_dir: Optional[str] = None
        self.jsonl_path: Optional[str] = None
        self.file_handle = None
        
        self.sample_count_total = 0
        self.sample_counts = defaultdict(int)
        self.first_timestamp = None
        self.last_timestamp = None

    def begin(self, session_id: str, instrument_id: str, metadata: dict):
        import re
        if self.file_handle is not None:
            raise RuntimeError('Finish or abort the current session before starting another.')
        if not isinstance(session_id, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}', session_id) is None or session_id in ('.', '..'):
            raise ValueError('Use a safe, unique session identifier.')
        self.acquisition_utc = datetime.now(timezone.utc).isoformat()
        self.session_id = session_id
        self.instrument_id = instrument_id
        self.session_dir = os.path.join(self.base_dir, session_id)
        os.makedirs(self.session_dir, exist_ok=False)
        
        with open(os.path.join(self.session_dir, "session.json"), "w") as f:
            json.dump({
                "session_id": session_id,
                "instrument_id": instrument_id,
                "start_utc": self.acquisition_utc,
                "metadata": metadata
            }, f, indent=2)
            
        self.jsonl_path = os.path.join(self.session_dir, "measurements.jsonl")
        self.file_handle = open(self.jsonl_path, "x")
        self.sample_count_total = 0
        self.sample_counts.clear()
        self.first_timestamp = None
        self.last_timestamp = None

    def append(self, measurement: Measurement):
        if not self.file_handle:
            raise RuntimeError("Cannot append: Session not started.")
            
        m_dict = asdict(measurement)
        m_dict["scientific_state"] = measurement.scientific_state.value
        
        json_str = json.dumps(m_dict, separators=(",", ":"))
        self.file_handle.write(json_str + "\n")
        
        self.sample_count_total += 1
        self.sample_counts[measurement.quantity] += 1
        
        if self.first_timestamp is None:
            self.first_timestamp = measurement.device_timestamp_ns
        self.last_timestamp = measurement.device_timestamp_ns

    def commit(self, dropped_counts: dict=None, rejected_count: int=0) -> dict:
        if not self.file_handle:
            raise RuntimeError("Cannot commit: Session not started.")
            
        self.file_handle.close()
        self.file_handle = None
        
        sha256_hash = hashlib.sha256()
        with open(self.jsonl_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
                
        artifact_hash = sha256_hash.hexdigest()
        
        with open(os.path.join(self.session_dir, "measurements.sha256"), "w") as f:
            f.write(artifact_hash)
            
        duration_s = 0.0
        if self.first_timestamp is not None and self.last_timestamp is not None and self.sample_count_total > 1:
            duration_s = (self.last_timestamp - self.first_timestamp) / 1e9
                
        return {
            "session_id": self.session_id,
            "instrument_id": self.instrument_id,
            "sample_count_total": self.sample_count_total,
            "sample_counts": dict(self.sample_counts),
            "duration_s": duration_s,
            "artifact_format": "jsonl/v1",
            "artifact_hash": artifact_hash,
            "artifact_sha256": artifact_hash,
            "artifact_path": os.path.abspath(self.jsonl_path),
            "acquisition_utc": self.acquisition_utc,
            "dropped_packet_counts": dropped_counts or {},
            "rejected_packet_counts": rejected_count
        }

    def abort(self, reason: str) -> dict:
        if not self.file_handle:
            return {}
            
        self.file_handle.close()
        self.file_handle = None
        
        sha256_hash = hashlib.sha256()
        with open(self.jsonl_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
                
        artifact_hash = sha256_hash.hexdigest()
        
        with open(os.path.join(self.session_dir, "measurements.sha256"), "w") as f:
            f.write(artifact_hash)
            
        duration_s = 0.0
        if self.first_timestamp is not None and self.last_timestamp is not None and self.sample_count_total > 1:
            duration_s = (self.last_timestamp - self.first_timestamp) / 1e9
            
        if self.session_dir:
            with open(os.path.join(self.session_dir, "ABORTED.txt"), "w") as f:
                f.write(f"Session aborted: {reason}\n")
                
        return {
            "status": "INTERRUPTED",
            "reason": reason,
            "session_id": self.session_id,
            "instrument_id": self.instrument_id,
            "sample_count_total": self.sample_count_total,
            "sample_counts": dict(self.sample_counts),
            "duration_s": duration_s,
            "artifact_format": "jsonl/v1",
            "artifact_hash": artifact_hash,
            "artifact_sha256": artifact_hash,
            "artifact_path": os.path.abspath(self.jsonl_path),
            "acquisition_utc": self.acquisition_utc,
            "last_sample_device_timestamp_ns": self.last_timestamp
        }
