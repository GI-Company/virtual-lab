from dataclasses import dataclass
from datetime import datetime
from typing import List
from virtual_lab.ai.proposals import ExperimentProposal

@dataclass
class HumanOverride:
    field: str
    original_value: float
    new_value: float

@dataclass
class HumanExperimentDraft:
    draft_id: str
    derived_from_proposal_id: str
    derived_from_proposal_hash: str
    original_context_hash: str

    disease_program_id: str
    disease_model_version: str
    compound_id: str
    evidence_snapshot_hash: str

    # We store the parameters directly for the draft
    dose_uM: float
    duration_h: float
    ensemble_size: int
    overrides: List[HumanOverride]

    created_at: datetime
    revision: int

def create_draft_from_proposal(proposal: ExperimentProposal, envelope_hash: str, proposal_id: str, context_hash: str) -> HumanExperimentDraft:
    import time
    return HumanExperimentDraft(
        draft_id=f"HUM-DRF-{int(time.time())}",
        derived_from_proposal_id=proposal_id,
        derived_from_proposal_hash=envelope_hash,
        original_context_hash=context_hash,
        disease_program_id=proposal.disease,
        disease_model_version="1.0", # Hardcoded for beta
        compound_id=proposal.compound,
        evidence_snapshot_hash="frozen-beta-evidence-hash",
        dose_uM=proposal.dose_uM,
        duration_h=48.0,
        ensemble_size=proposal.ensemble_size,
        overrides=[],
        created_at=datetime.now(),
        revision=1
    )
