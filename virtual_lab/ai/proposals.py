from pydantic import BaseModel, Field
from typing import List

class FixedOverride(BaseModel):
    parameter_name: str
    value: float

class ParameterSweep(BaseModel):
    parameter_name: str
    distribution: str
    min_multiplier: float
    max_multiplier: float

class ParameterChanges(BaseModel):
    fixed_overrides: List[FixedOverride] = Field(default_factory=list)
    sweeps: List[ParameterSweep] = Field(default_factory=list)

class ExperimentProposal(BaseModel):
    operation: str = Field(description="Type of operation, e.g., POPULATION_COUNTERFACTUAL")
    disease: str = Field(description="Disease model identifier, e.g., rho_p23h")
    compound: str = Field(description="Compound identifier, e.g., YC-001 (EMPIRICAL) or YC-054 [PREDICTED PARAMETERS / INCOMPLETE]")
    ensemble_size: int = Field(description="Number of virtual systems to simulate (ensemble members)")
    dose_uM: float = Field(description="Dose concentration in µM")
    parameter_changes: ParameterChanges = Field(default_factory=ParameterChanges, description="Proposed mechanistic overrides")
    outputs: List[str] = Field(description="List of states to track, e.g., ['R_s', 'S', 'V']")
    rationale: str = Field(description="Scientific rationale for this proposed experiment")
