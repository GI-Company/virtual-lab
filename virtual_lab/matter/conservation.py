from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class ConservationReport:
    element_balance: Dict[str, float]
    charge_before: int
    charge_after: int
    mass_before_u: float
    mass_after_u: float
    
    @property
    def is_conserved(self) -> bool:
        # Check charge
        if self.charge_before != self.charge_after:
            return False
            
        # Check mass strictly
        if abs(self.mass_before_u - self.mass_after_u) > 1e-6:
            return False
            
        # Check elements
        for element, delta in self.element_balance.items():
            if abs(delta) > 1e-6:
                return False
                
        return True
