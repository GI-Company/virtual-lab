from dataclasses import dataclass
from typing import Optional, Any
from .base import Identity, State
from .isotopes import IsotopeIdentity

@dataclass(frozen=True)
class AtomIdentity(Identity):
    isotope: IsotopeIdentity
    
    @property
    def element(self):
        return self.isotope.element

@dataclass(frozen=True)
class AtomState(State):
    identity: AtomIdentity
    electron_count: int
    position_m: Optional[Any] = None # Using ArrayBackend eventually
    
    @property
    def formal_charge(self) -> int:
        return self.identity.isotope.proton_count - self.electron_count
