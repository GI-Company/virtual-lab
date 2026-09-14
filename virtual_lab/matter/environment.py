from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Environment:
    temperature_K: float = 298.15
    pressure_Pa: float = 101325.0
    pH: Optional[float] = None
    solvent: Optional[str] = None
    ionic_strength_mol_m3: Optional[float] = None
