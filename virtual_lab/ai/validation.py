from typing import List, Tuple
from .proposals import ExperimentProposal
from .context import ScientificContext

class ValidationEngine:
    """Enforces scientific permissions and rule sets over AI proposals."""
    
    @staticmethod
    def validate_proposal(proposal: ExperimentProposal, context: ScientificContext) -> Tuple[bool, str]:
        # 1. Verify disease model matches
        if proposal.disease != context.disease_model_id:
            return False, f"Proposal targets {proposal.disease} but context is {context.disease_model_id}."
            
        # 2. Prevent MUTATE_EVIDENCE (direct rewrite of measured parameters)
        # Note: We allow OVERRIDE_PARAMETER_IN_BRANCH as long as it's structurally valid in the proposal,
        # but we do not allow proposals that explicitly try to change the base epistemic state.
        # Since the AI only outputs ExperimentProposal, the act of proposing an override is inherently
        # branching. We just need to verify the targeted parameters exist.
        for override in proposal.parameter_changes.fixed_overrides:
            if override.parameter_name not in context.parameter_values:
                return False, f"Invalid override target: {override.parameter_name} does not exist."
                
        for sweep in proposal.parameter_changes.sweeps:
            if sweep.parameter_name not in context.parameter_values:
                return False, f"Invalid sweep target: {sweep.parameter_name} does not exist."
                
            if sweep.min_multiplier > sweep.max_multiplier:
                return False, f"Sweep {sweep.parameter_name} has min > max."
                
            # Basic sanity check to prevent insane physical multipliers
            if sweep.min_multiplier < 0.0 or sweep.max_multiplier > 1000.0:
                return False, f"Sweep {sweep.parameter_name} has biologically absurd multipliers."

        return True, "Valid proposal."
