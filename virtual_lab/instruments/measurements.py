from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum

class ScientificState(Enum):
    MEASURED = "MEASURED"
    DERIVED = "DERIVED"
    PREDICTED = "PREDICTED"
    SIMULATED = "SIMULATED"

@dataclass(frozen=True)
class Measurement:
    measurement_id: str
    session_id: str
    source_session_id: Optional[str]
    instrument_id: str
    sensor_id: str

    sequence: int

    device_timestamp_ns: int
    received_monotonic_ns: int
    received_utc_ns: int

    quantity: str
    values: Dict[str, float]
    units: Dict[str, str]

    sensor_accuracy: Optional[int]
    calibration_id: Optional[str]

    scientific_state: ScientificState
