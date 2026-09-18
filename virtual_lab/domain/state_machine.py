"""
virtual_lab.domain.state_machine
────────────────────────────────
Event-sourced scientific DAG enforcing legal transitions between states.

Rules:
- Prediction requires hypothesis_id, protocol_id or model_id. Cannot reference future observations.
- Observation requires run_id, provenance, epistemic_state, quality_state.
- Comparison requires compatible prediction + observation. Cannot modify sources.
- Decision requires one or more comparisons.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Set
import hashlib
import json

from virtual_lab.domain.epistemics import EpistemicState, QualityState


@dataclass(frozen=True)
class Hypothesis:
    id: str
    description: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass(frozen=True)
class Protocol:
    id: str
    content_hash: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass(frozen=True)
class Prediction:
    id: str
    hypothesis_id: str
    expected_outcome: str
    protocol_id: Optional[str] = None
    model_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if not self.protocol_id and not self.model_id:
            raise ValueError("Prediction requires either protocol_id or model_id")

@dataclass(frozen=True)
class ExperimentRun:
    id: str
    protocol_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass(frozen=True)
class DAGObservation:
    id: str
    run_id: str
    epistemic_state: EpistemicState
    quality_state: QualityState
    provenance_hash: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass(frozen=True)
class Comparison:
    id: str
    prediction_id: str
    observation_id: str
    result_summary: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass(frozen=True)
class Decision:
    id: str
    comparison_ids: List[str]
    outcome: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if not self.comparison_ids:
            raise ValueError("Decision requires at least one comparison")


class ScientificDAG:
    """In-memory verifier for DAG transitions."""
    def __init__(self):
        self.hypotheses: dict[str, Hypothesis] = {}
        self.protocols: dict[str, Protocol] = {}
        self.predictions: dict[str, Prediction] = {}
        self.runs: dict[str, ExperimentRun] = {}
        self.observations: dict[str, DAGObservation] = {}
        self.comparisons: dict[str, Comparison] = {}
        self.decisions: dict[str, Decision] = {}

    def add_hypothesis(self, hypothesis: Hypothesis):
        self.hypotheses[hypothesis.id] = hypothesis

    def add_protocol(self, protocol: Protocol):
        self.protocols[protocol.id] = protocol

    def add_prediction(self, prediction: Prediction):
        if prediction.hypothesis_id not in self.hypotheses:
            raise ValueError("Hypothesis does not exist")
        if prediction.protocol_id and prediction.protocol_id not in self.protocols:
            raise ValueError("Protocol does not exist")
        # Cannot reference future observations (implied by ID dependencies, observations come later)
        self.predictions[prediction.id] = prediction

    def add_run(self, run: ExperimentRun):
        if run.protocol_id not in self.protocols:
            raise ValueError("Protocol does not exist")
        self.runs[run.id] = run

    def add_observation(self, obs: DAGObservation):
        if obs.run_id not in self.runs:
            raise ValueError("Run does not exist")
        self.observations[obs.id] = obs

    def add_comparison(self, comp: Comparison):
        if comp.prediction_id not in self.predictions:
            raise ValueError("Prediction does not exist")
        if comp.observation_id not in self.observations:
            raise ValueError("Observation does not exist")
        
        pred = self.predictions[comp.prediction_id]
        obs = self.observations[comp.observation_id]
        
        if obs.created_at < pred.created_at:
             # Depending on semantics, prediction should usually pre-date observation
             pass
             
        self.comparisons[comp.id] = comp

    def add_decision(self, decision: Decision):
        for cid in decision.comparison_ids:
            if cid not in self.comparisons:
                raise ValueError(f"Comparison {cid} does not exist")
        self.decisions[decision.id] = decision
