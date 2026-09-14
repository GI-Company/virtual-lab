import numpy as np
from typing import Any, Tuple
from .backend import ArrayBackend

class NumPyBackend:
    name = "numpy"

    def array(self, data: Any, *, dtype: Any = None) -> np.ndarray:
        return np.array(data, dtype=dtype)

    def zeros(self, shape: Tuple[int, ...], *, dtype: Any = None) -> np.ndarray:
        return np.zeros(shape, dtype=dtype)

    def to_numpy(self, value: np.ndarray) -> np.ndarray:
        return np.asarray(value)

# Singleton backend for defaults
default_backend: ArrayBackend = NumPyBackend()
