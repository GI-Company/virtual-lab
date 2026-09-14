from dataclasses import dataclass
from typing import Optional, Protocol, Any
from .serialization import serialize_dataclass
from .hashing import deterministic_hash

@dataclass(frozen=True)
class Identity:
    """Base class for all matter identities (e.g., specific molecule, isotope)."""
    @property
    def identity_hash(self) -> str:
        data = serialize_dataclass(self)
        # We explicitly inject a type marker so that an Atom isn't hashed the same as an Isotope with identical fields
        data["__identity_type__"] = self.__class__.__name__
        return deterministic_hash(data)

@dataclass(frozen=True)
class State:
    """Base class for matter states (e.g., conformer of a molecule, ion)."""
    identity: Identity
    
    @property
    def state_hash(self) -> str:
        data = serialize_dataclass(self)
        data["__state_type__"] = self.__class__.__name__
        return deterministic_hash(data)
