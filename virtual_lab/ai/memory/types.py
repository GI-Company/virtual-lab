from enum import Enum, auto

class MemoryClass(Enum):
    SEMANTIC = auto()
    EPISODIC = auto()
    PROCEDURAL = auto()

class AuthoritativeResolutionState(Enum):
    VALID = auto()
    STALE = auto()
    MISSING = auto()
    HASH_MISMATCH = auto()
    STORE_UNAVAILABLE = auto()

class TemporalBasis(Enum):
    EVENT_TIME = auto()
    EXPERIMENT_TIME = auto()
    NONE = auto()

class Scope(Enum):
    GLOBAL = auto()
    EXPERIMENT_LOCAL = auto()
    CROSS_EXPERIMENT_EXPLICIT = auto()
