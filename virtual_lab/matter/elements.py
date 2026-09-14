from dataclasses import dataclass
from typing import Dict, Optional
from .base import Identity

@dataclass(frozen=True)
class ElementIdentity(Identity):
    atomic_number: int
    symbol: str
    name: str

# A basic registry for v0.1
ELEMENTS: Dict[int, ElementIdentity] = {
    1: ElementIdentity(1, "H", "Hydrogen"),
    6: ElementIdentity(6, "C", "Carbon"),
    7: ElementIdentity(7, "N", "Nitrogen"),
    8: ElementIdentity(8, "O", "Oxygen"),
    11: ElementIdentity(11, "Na", "Sodium"),
    15: ElementIdentity(15, "P", "Phosphorus"),
    16: ElementIdentity(16, "S", "Sulfur"),
    17: ElementIdentity(17, "Cl", "Chlorine"),
}

def get_element(atomic_number: int) -> ElementIdentity:
    if atomic_number not in ELEMENTS:
        raise ValueError(f"Element with atomic number {atomic_number} not in registry.")
    return ELEMENTS[atomic_number]
