from __future__ import annotations
from typing import Any, Dict

class Engine:
    """Base class for all VirtualLab engines."""
    name: str = "BaseEngine"
    version: str = "0.1"

    def validate(self, experiment: Any) -> bool:
        """Validate if this engine can run the given experiment."""
        return True

    def run(self, experiment: Any) -> Dict[str, Any]:
        """Execute the engine logic on the experiment. Must be overridden."""
        raise NotImplementedError("Engines must implement the run() method.")
