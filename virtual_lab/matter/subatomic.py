from dataclasses import dataclass
from typing import ClassVar
from .base import Identity

@dataclass(frozen=True)
class SubatomicParticle(Identity):
    """Representational class for subatomic particles. Do NOT instantiate billions of these."""
    rest_mass_u: float
    charge_e: int

@dataclass(frozen=True)
class Proton(SubatomicParticle):
    rest_mass_u: float = 1.007276466621
    charge_e: int = 1

@dataclass(frozen=True)
class Neutron(SubatomicParticle):
    rest_mass_u: float = 1.00866491595
    charge_e: int = 0

@dataclass(frozen=True)
class Electron(SubatomicParticle):
    rest_mass_u: float = 0.000548579909
    charge_e: int = -1

# Singletons for representation
PROTON = Proton()
NEUTRON = Neutron()
ELECTRON = Electron()
