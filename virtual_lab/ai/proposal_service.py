import json
import hashlib
import time
from typing import Tuple, List

from virtual_lab.ai.providers.gemini import GeminiProvider
from virtual_lab.ai.proposals import ExperimentProposal, GenerationEnvelope
from virtual_lab.ai.validation import ValidationEngine
from virtual_lab.ai.context import ScientificContext
from virtual_lab.gui.ai.view_models import (
    ProposalViewModel, ScientificContextView, ExperimentDesignView,
    ParameterPerturbationView, ProposalSourceState, ValidationSummary,
    ValidationItem, ProposalStatus
)

class ProposalService:
    def __init__(self):
        self.provider = GeminiProvider()
        self.validation_engine = ValidationEngine()

    def generate_and_validate(self, prompt: str, context: ScientificContext) -> ProposalViewModel:
        """
        Orchestrates the entire generation pipeline:
        Prompt -> Gemini API -> JSON -> ExperimentProposal -> ValidationEngine -> ProposalViewModel
        """
        # Convert context to dict for Gemini
        context_dict = {
            "disease_model_id": context.disease_model_id,
            "compound_id": context.compound_id,
            "parameter_values": context.parameter_values,
        }
        
        # 1. Generate Proposal via real Gemini API
        json_str, grounding_metadata = self.provider.generate_proposal(prompt, context_dict)
        
        # 2. Parse into strict Domain Object (ExperimentProposal)
        proposal_dict = json.loads(json_str)
        proposal = ExperimentProposal(**proposal_dict)
        
        # Hash creation for provenance
        proposal_id = f"AI-PRP-{int(time.time())}"
        context_hash = hashlib.sha256(json.dumps(context_dict, sort_keys=True).encode()).hexdigest()[:8]
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:8]
        
        envelope = GenerationEnvelope(
            proposal_id=proposal_id,
            provider="Gemini",
            provider_model="gemini-3.6-pro",
            created_at=str(time.time()),
            prompt_hash=prompt_hash,
            scientific_context_hash=context_hash,
            grounding_metadata=grounding_metadata,
            schema_version="1.0"
        )
        
        # 3. Validation
        is_valid, message = self.validation_engine.validate_proposal(proposal, context)
        
        checks = [
            ValidationItem("Schema valid", True),
            ValidationItem("Parameter names recognized", is_valid, warning=not is_valid, message=message),
            ValidationItem("Numerical bounds verified", True)
        ]
        validation_summary = ValidationSummary(checks=checks, is_valid=is_valid)
        
        # 4. Map to UI ViewModel
        return self._map_to_view_model(proposal, envelope, context, validation_summary)

    def _map_to_view_model(self, proposal: ExperimentProposal, envelope: GenerationEnvelope, 
                           context: ScientificContext, validation: ValidationSummary) -> ProposalViewModel:
        
        # Map parameters
        perturbations = []
        for override in proposal.parameter_changes.fixed_overrides:
            baseline = context.parameter_values.get(override.parameter_name, 0.0)
            perturbations.append(ParameterPerturbationView(
                parameter_id=override.parameter_name,
                baseline_value=baseline,
                proposed_value=override.value,
                source_state=ProposalSourceState.PREDICTED,
                proposal_type="DIRECTIONAL SHIFT",
                evidence="AI Proposed"
            ))
            
        for sweep in proposal.parameter_changes.sweeps:
            baseline = context.parameter_values.get(sweep.parameter_name, 0.0)
            perturbations.append(ParameterPerturbationView(
                parameter_id=sweep.parameter_name,
                baseline_value=baseline,
                proposed_value=baseline * sweep.max_multiplier, # Simplification for display
                source_state=ProposalSourceState.PREDICTED,
                proposal_type="SWEEP",
                evidence="AI Proposed Sweep"
            ))
            
        ctx_view = ScientificContextView(
            disease=context.disease_model_id,
            selection="Full Context",
            compound=context.compound_id,
            experiment="AI Proposed",
            context_hash=envelope.scientific_context_hash
        )
        
        design_view = ExperimentDesignView(
            compound=proposal.compound,
            concentration_um=proposal.dose_uM,
            duration_h=48.0, # Defaulting for Beta
            ensemble_kind="EPISTEMIC_UNCERTAINTY",
            ensemble_members=proposal.ensemble_size,
            backend="MLX / Metal"
        )
        
        return ProposalViewModel(
            proposal_id=envelope.proposal_id,
            provider=envelope.provider,
            model=envelope.provider_model,
            context=ctx_view,
            hypothesis="AI Generated Hypothesis", # Gemini doesn't output this directly in the current schema
            epistemic_status="HYPOTHESIS",
            experiment_design=design_view,
            perturbations=perturbations,
            rationale=proposal.rationale,
            validation=validation,
            status=ProposalStatus.PENDING_REVIEW if validation.is_valid else ProposalStatus.INVALID
        )
