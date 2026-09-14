from typing import Protocol

class ExposureModel(Protocol):
    def concentration(self, t: float) -> float:
        """Returns the external compound concentration at time t. Must be in normalized canonical units (e.g. uM)."""
        ...

class ConstantExposure(ExposureModel):
    def __init__(self, external_compound_concentration: float):
        """external_compound_concentration should be in standard canonical units defined by the model (e.g. uM)."""
        self._c = external_compound_concentration
        
    def concentration(self, t: float) -> float:
        return self._c
