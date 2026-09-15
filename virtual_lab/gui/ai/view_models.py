from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class ProposalStatus(Enum):
    GENERATING = "GENERATING"
    RECEIVED = "RECEIVED"
    INVALID = "INVALID"
    VALIDATED = "VALIDATED"
    PENDING_REVIEW = "PENDING REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    EXECUTED = "EXECUTED"

class ProposalSourceState(Enum):
    MEASURED = "MEASURED"
    CURATED = "CURATED"
    DERIVED = "DERIVED"
    PREDICTED = "PREDICTED"
    MODEL_ASSUMPTION = "MODEL_ASSUMPTION"
    HYPOTHETICAL = "HYPOTHETICAL"
    COUNTERFACTUAL = "COUNTERFACTUAL"

@dataclass(frozen=True)
class ValidationItem:
    label: str
    passed: bool
    warning: bool = False
    message: str = ""

@dataclass(frozen=True)
class ValidationSummary:
    checks: List[ValidationItem]
    is_valid: bool

@dataclass(frozen=True)
class ParameterPerturbationView:
    parameter_id: str
    baseline_value: float
    proposed_value: float
    source_state: ProposalSourceState
    proposal_type: str
    evidence: str

    @property
    def delta_pct(self) -> float:
        if self.baseline_value == 0:
            return 0.0
        return ((self.proposed_value - self.baseline_value) / self.baseline_value) * 100.0

@dataclass(frozen=True)
class ExperimentDesignView:
    compound: str
    concentration_um: float
    duration_h: float
    ensemble_kind: str
    ensemble_members: int
    backend: str

@dataclass(frozen=True)
class ScientificContextView:
    disease: str
    selection: str
    compound: str
    experiment: str
    context_hash: str

@dataclass(frozen=True)
class ProposalViewModel:
    proposal_id: str
    provider: str
    model: str
    context: ScientificContextView
    
    hypothesis: str
    epistemic_status: str

    experiment_design: ExperimentDesignView
    perturbations: List[ParameterPerturbationView]

    rationale: str
    validation: Optional[ValidationSummary]

    status: ProposalStatus

@dataclass(frozen=True)
class GateDecision:
    label: str
    status: str # PASS, FAIL, WARN

@dataclass(frozen=True)
class CorpusAuditViewModel:
    snapshot_id: str
    compounds_discovered: int
    eligible_compounds: int
    eligible_assay_records: int
    
    exact_endpoint_compatible: int
    identity_unresolved: int
    structural_violations: int
    unit_normalization_failures: int
    censored_measurements_preserved: int
    
    ml_training_gate_passed: bool
    gate_reason: str
    gate_required: int
    gate_available: int
    
    gate_decisions: List[GateDecision]
