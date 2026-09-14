from dataclasses import dataclass
from typing import Any, Optional
from .units import to_canonical

@dataclass(frozen=True)
class ScientificValue:
    """Represents a dimensionally correct value with epistemic tracking and uncertainty."""
    value: float
    unit: str
    uncertainty: Optional[float] = None
    method: str = "UNKNOWN"
    
    @property
    def canonical_value(self) -> float:
        """Return the value converted to canonical internal SI units."""
        return to_canonical(self.value, self.unit)
        
    @property
    def canonical_uncertainty(self) -> Optional[float]:
        if self.uncertainty is None:
            return None
        return to_canonical(self.uncertainty, self.unit)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "unit": self.unit,
            "uncertainty": self.uncertainty,
            "method": self.method
        }
