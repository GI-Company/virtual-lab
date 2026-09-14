from dataclasses import dataclass
from typing import Tuple, Optional
from .base import State
from .molecular import MoleculeState
from .environment import Environment

@dataclass(frozen=True)
class Component:
    molecule: MoleculeState
    amount_mol: float

@dataclass(frozen=True)
class MixtureState(State):
    components: Tuple[Component, ...]
    environment: Environment
    volume_m3: float
    
    @property
    def identity(self):
        # The mixture is a state; it is a macro-state of multiple identities
        # This simplifies the v0.1 approach for macroscopic states
        return None
