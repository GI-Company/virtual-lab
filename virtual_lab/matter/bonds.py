from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class Bond:
    """Graph edge representing a chemical bond."""
    atom_indices: Tuple[int, int]
    order: float
    is_aromatic: bool = False
