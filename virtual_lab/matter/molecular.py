from dataclasses import dataclass
from typing import Tuple, Dict, Any, Optional
from .base import Identity, State
from .atomic import AtomIdentity
from .bonds import Bond

@dataclass(frozen=True)
class MoleculeIdentity(Identity):
    atoms: Tuple[AtomIdentity, ...]
    bonds: Tuple[Bond, ...]
    stereochemistry: Dict[str, Any]
    
    @property
    def monoisotopic_mass_u(self) -> float:
        """Sum of the measured masses of the constituent exact isotopes."""
        return sum(atom.isotope.measured_atomic_mass_u for atom in self.atoms)

@dataclass(frozen=True)
class MoleculeState(State):
    identity: MoleculeIdentity
    formal_charges: Tuple[int, ...]
    conformer: Optional[Any] = None # Will be array from backend
    electronic_state: str = "singlet"
    environment_ref: Optional[str] = None
