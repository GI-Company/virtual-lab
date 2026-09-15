import typing
from pydantic import BaseModel, Field

# We use Pydantic models for explicit schema validation in the Agent loop,
# though the google-genai SDK also supports raw Python functions.

class CreateProposalArgs(BaseModel):
    hypothesis: str = Field(description="The scientific hypothesis being tested.")
    operation: str = Field(description="Type of operation, e.g., POPULATION_COUNTERFACTUAL")
    disease: str = Field(description="Disease model identifier, e.g., rho_p23h")
    compound: str = Field(description="Compound identifier, e.g., YC-001 (EMPIRICAL) or YC-054 [PREDICTED PARAMETERS / INCOMPLETE]")
    ensemble_size: int = Field(description="Number of virtual systems to simulate (ensemble members)")
    dose_uM: float = Field(description="Dose concentration in µM")
    outputs: list[str] = Field(description="List of states to track, e.g., ['R_s', 'S', 'V']")
    rationale: str = Field(description="Scientific rationale for this proposed experiment")
    overrides: dict[str, float] = Field(description="Dictionary mapping parameter names to their proposed override values.")

class ExecuteExperimentArgs(BaseModel):
    proposal_id: str = Field(description="The ID of the proposal to execute.")

class ReadSimulationResultsArgs(BaseModel):
    run_id: str = Field(description="The ID of the simulation run to read.")

def create_and_validate_proposal(hypothesis: str, operation: str, disease: str, compound: str, ensemble_size: int, dose_uM: float, outputs: list[str], rationale: str, overrides: dict[str, float]) -> str:
    """
    Creates an experiment proposal and validates it against the current epistemic state.
    Returns the proposal_id if successful.
    """
    # This is a stub function. The actual execution will be intercepted by the AgentWorker
    # and passed to the ProposalService.
    pass

def execute_experiment(proposal_id: str) -> str:
    """
    Executes a previously created proposal.
    Returns the run_id of the executed experiment.
    """
    # Stub function. Execution intercepted by AgentWorker and passed to ExperimentController.
    pass

def read_simulation_results(run_id: str) -> str:
    """
    Reads the results of a completed simulation run.
    Returns a summary of the epistemic outcomes.
    """
    # Stub function. Execution intercepted by AgentWorker.
    pass

# The list of callable tools for the Gemini SDK
AGENT_TOOLS = [
    create_and_validate_proposal,
    execute_experiment,
    read_simulation_results
]
