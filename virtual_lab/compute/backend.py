from typing import Protocol, Any, Tuple

class ArrayBackend(Protocol):
    name: str

    def array(self, data: Any, *, dtype: Any = None) -> Any:
        ...

    def zeros(self, shape: Tuple[int, ...], *, dtype: Any = None) -> Any:
        ...

    def to_numpy(self, value: Any) -> Any:
        ...
