from typing import Dict, Type
from virtual_lab.engines.base import Engine

class EngineRegistry:
    _engines: Dict[str, Engine] = {}

    @classmethod
    def register(cls, engine: Engine):
        cls._engines[engine.name] = engine

    @classmethod
    def get(cls, name: str) -> Engine:
        if name not in cls._engines:
            raise ValueError(f"Engine '{name}' not found in registry.")
        return cls._engines[name]
