from .backend import ArrayBackend
from .numpy_backend import default_backend

_current_backend: ArrayBackend = default_backend

def set_backend(backend: ArrayBackend):
    global _current_backend
    _current_backend = backend

def get_backend() -> ArrayBackend:
    return _current_backend
