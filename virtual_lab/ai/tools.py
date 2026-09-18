import typing
from pydantic import BaseModel, Field

# Operational PoC v0.1: L1 Autonomy Constraint
# The model can only read context and propose state changes. It has ZERO execution authority.

class GetHypothesisArgs(BaseModel):
    id: str = Field(description="The ID of the hypothesis to retrieve.")

class ProposePredictionArgs(BaseModel):
    hypothesis_id: str = Field(description="The hypothesis this prediction supports.")
    expected_outcome: str = Field(description="The predicted outcome.")
    rationale: str = Field(description="Scientific rationale for this prediction.")

class ProposeComparisonArgs(BaseModel):
    prediction_id: str = Field(description="The prediction to compare.")
    observation_id: str = Field(description="The observation to compare against.")

def get_hypothesis(id: str) -> str:
    """Retrieve an existing hypothesis from the authoritative state."""
    pass

def get_protocol(id: str) -> str:
    """Retrieve a frozen protocol."""
    pass

def get_prediction(id: str) -> str:
    """Retrieve a frozen prediction."""
    pass

def get_observation(id: str) -> str:
    """Retrieve an observation."""
    pass

def search_evidence(query: str) -> str:
    """Search for relevant evidence in the vault."""
    pass

def propose_hypothesis(description: str) -> str:
    """Propose a new hypothesis for human review. Does NOT create authoritative truth."""
    pass

def propose_prediction(hypothesis_id: str, expected_outcome: str, rationale: str) -> str:
    """Propose a prediction."""
    pass

def propose_comparison(prediction_id: str, observation_id: str) -> str:
    """Propose comparing an observation to a prediction."""
    pass

def propose_decision(comparison_ids: list[str], outcome: str) -> str:
    """Propose a scientific decision based on comparisons."""
    pass

def request_human_approval(proposal_id: str) -> str:
    """Submit a proposal to the human operator for Ed25519 signature."""
    pass

def explain_provenance(id: str) -> str:
    """Retrieve the Genesis audit trail for an object."""
    pass

AGENT_TOOLS = [
    get_hypothesis,
    get_protocol,
    get_prediction,
    get_observation,
    search_evidence,
    propose_hypothesis,
    propose_prediction,
    propose_comparison,
    propose_decision,
    request_human_approval,
    explain_provenance
]
