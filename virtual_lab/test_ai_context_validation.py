import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from virtual_lab.ai.context import ScientificContext, generate_context_hash
from virtual_lab.ai.proposals import ExperimentProposal, ParameterChanges, ParameterSweep, FixedOverride
from virtual_lab.ai.validation import ValidationEngine

def test_context_hashing():
    ctx1 = ScientificContext(
        context_id="CTX-1",
        disease_model_id="rho_p23h",
        disease_model_hash="hash1",
        experiment_id="EXP-1",
        experiment_hash="hash2",
        state_schema=["R_s"],
        state_constraints={},
        parameter_values={"k_ERAD": 0.5},
        parameter_epistemics={"k_ERAD": "MEASURED"},
        parameter_uncertainties={"k_ERAD": 0.1},
        exposure_model="ConstantExposure",
        compound_identity="YC-054 [PREDICTED PARAMETERS / INCOMPLETE]",
        evidence_snapshot_hash="evhash",
        mechanism_graph_hash="mechhash",
        simulation_backend="metal",
        numerical_validation="PASSED"
    )
    
    # Same data, different instance
    ctx2 = ScientificContext(
        context_id="CTX-1",
        disease_model_id="rho_p23h",
        disease_model_hash="hash1",
        experiment_id="EXP-1",
        experiment_hash="hash2",
        state_schema=["R_s"],
        state_constraints={},
        parameter_values={"k_ERAD": 0.5},
        parameter_epistemics={"k_ERAD": "MEASURED"},
        parameter_uncertainties={"k_ERAD": 0.1},
        exposure_model="ConstantExposure",
        compound_identity="YC-054 [PREDICTED PARAMETERS / INCOMPLETE]",
        evidence_snapshot_hash="evhash",
        mechanism_graph_hash="mechhash",
        simulation_backend="metal",
        numerical_validation="PASSED"
    )
    
    hash1 = generate_context_hash(ctx1)
    hash2 = generate_context_hash(ctx2)
    assert hash1 == hash2

def test_proposal_validation():
    ctx = ScientificContext(
        context_id="CTX-1",
        disease_model_id="rho_p23h",
        disease_model_hash="hash1",
        experiment_id="EXP-1",
        experiment_hash="hash2",
        state_schema=["R_s"],
        state_constraints={},
        parameter_values={"k_ERAD": 0.5},
        parameter_epistemics={"k_ERAD": "MEASURED"},
        parameter_uncertainties={"k_ERAD": 0.1},
        exposure_model="ConstantExposure",
        compound_identity="YC-054 [PREDICTED PARAMETERS / INCOMPLETE]",
        evidence_snapshot_hash="evhash",
        mechanism_graph_hash="mechhash",
        simulation_backend="metal",
        numerical_validation="PASSED"
    )
    
    valid_proposal = ExperimentProposal(
        operation="POPULATION_COUNTERFACTUAL",
        disease="rho_p23h",
        compound="YC-054 [PREDICTED PARAMETERS / INCOMPLETE]",
        ensemble_size=1000,
        dose_uM=2.0,
        parameter_changes=ParameterChanges(
            sweeps=[ParameterSweep(parameter_name="k_ERAD", distribution="uniform", min_multiplier=0.5, max_multiplier=1.5)]
        ),
        outputs=["R_s"],
        rationale="Test ERAD sensitivity."
    )
    
    is_valid, msg = ValidationEngine.validate_proposal(valid_proposal, ctx)
    assert is_valid
    
    invalid_proposal = ExperimentProposal(
        operation="POPULATION_COUNTERFACTUAL",
        disease="rho_p23h",
        compound="YC-054 [PREDICTED PARAMETERS / INCOMPLETE]",
        ensemble_size=1000,
        dose_uM=2.0,
        parameter_changes=ParameterChanges(
            sweeps=[ParameterSweep(parameter_name="k_MAGIC", distribution="uniform", min_multiplier=0.5, max_multiplier=1.5)]
        ),
        outputs=["R_s"],
        rationale="Test magic."
    )
    
    is_valid, msg = ValidationEngine.validate_proposal(invalid_proposal, ctx)
    assert not is_valid
    assert "k_MAGIC does not exist" in msg
