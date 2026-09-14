from dataclasses import dataclass
from typing import Dict, Tuple
from .base import Identity
from .elements import ElementIdentity, get_element
from .subatomic import PROTON, NEUTRON, ELECTRON

@dataclass(frozen=True)
class IsotopeIdentity(Identity):
    element: ElementIdentity
    mass_number: int
    measured_atomic_mass_u: float
    
    @property
    def proton_count(self) -> int:
        return self.element.atomic_number
        
    @property
    def neutron_count(self) -> int:
        return self.mass_number - self.proton_count
        
    @property
    def constituent_rest_mass_sum_u(self) -> float:
        """Sum of free protons, neutrons, and electrons (for a neutral atom)."""
        return (self.proton_count * PROTON.rest_mass_u + 
                self.neutron_count * NEUTRON.rest_mass_u + 
                self.proton_count * ELECTRON.rest_mass_u)
                
    @property
    def mass_defect_u(self) -> float:
        """Difference between constituent rest mass sum and actual measured mass."""
        return self.constituent_rest_mass_sum_u - self.measured_atomic_mass_u

# Registry of isotopes
ISOTOPES: Dict[Tuple[int, int], IsotopeIdentity] = {
    (1, 1): IsotopeIdentity(get_element(1), 1, 1.00782503224),
    (1, 2): IsotopeIdentity(get_element(1), 2, 2.01410177811),
    (6, 12): IsotopeIdentity(get_element(6), 12, 12.0000000),
    (6, 13): IsotopeIdentity(get_element(6), 13, 13.00335483507),
    (7, 14): IsotopeIdentity(get_element(7), 14, 14.0030740044),
    (8, 16): IsotopeIdentity(get_element(8), 16, 15.99491461956),
    (11, 23): IsotopeIdentity(get_element(11), 23, 22.9897692820),
    (17, 35): IsotopeIdentity(get_element(17), 35, 34.9688527),
}

def get_isotope(atomic_number: int, mass_number: int) -> IsotopeIdentity:
    key = (atomic_number, mass_number)
    if key not in ISOTOPES:
        raise ValueError(f"Isotope Z={atomic_number}, A={mass_number} not in registry.")
    return ISOTOPES[key]
