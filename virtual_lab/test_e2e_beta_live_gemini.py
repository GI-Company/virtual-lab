import pytest
import os
import sys
import tempfile
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from virtual_lab.core.ledger import GenesisLedger, Actor
from virtual_lab.ai.context import ScientificContext, generate_context_hash
from virtual_lab.ai.validation import ValidationEngine
from virtual_lab.ai.providers import get_provider
from virtual_lab.ai.base import IntelligenceRequest
from virtual_lab.diseases.rho_p23h.model import RhoP23HModel

@pytest.mark.skipif(
    os.environ.get("VIRTUALLAB_RUN_LIVE_AI_TESTS") != "1",
    reason="Live Gemini E2E tests require VIRTUALLAB_RUN_LIVE_AI_TESTS=1"
)
def test_live_gemini_e2e():
    """
    Runs an E2E pipeline hitting the actual Gemini API.
    Ensure Keychain has a valid Gemini API key.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "ledger_live.db")
        ledger = GenesisLedger(db_path)
        
        prompt = "Compare YC-001 across 10 uncertainty realizations of the P23H model. Vary k_ERAD and k_traffic."
        human_actor = Actor(type="HUMAN", id="user-1")
        ledger.append("EVT-1", human_actor, "PROMPT_RECEIVED", {"prompt": prompt})
        
        model = RhoP23HModel()
        ctx = ScientificContext(
            context_id="CTX-1",
            disease_model_id="rho_p23h",
            disease_model_hash="hash1",
            experiment_id="EXP-1",
            experiment_hash="hash2",
            state_schema=model.state_schema(),
            state_constraints={str(k): v for k, v in model.state_constraints().items()},
            parameter_values={k: v.value for k, v in model.parameters().items()},
            parameter_epistemics={k: "KNOWN" for k in model.parameters().keys()},
            parameter_uncertainties={k: 0.1 for k in model.parameters().keys()},
            exposure_model="ConstantExposure",
            compound_identity="YC-001",
            evidence_snapshot_hash="evhash",
            mechanism_graph_hash="mechhash",
            simulation_backend="mlx",
            numerical_validation="PENDING"
        )
        ctx_hash = generate_context_hash(ctx)
        ledger.append("EVT-2", Actor(type="SYSTEM", id="desktop"), "CONTEXT_FROZEN", {"context_hash": ctx_hash})
        
        provider = get_provider("gemini")
        req = IntelligenceRequest(
            system_prompt="You are a scientific AI. Respond ONLY with a valid ExperimentProposal JSON specifying how to vary parameters (k_ERAD, etc) using sweeps.",
            user_prompt=prompt,
            context_hash=ctx_hash,
            require_structured_output=True
        )
        
        response = provider.complete(req)
        
        assert response.proposal is not None, f"Failed to get structured proposal. Raw text: {response.raw_text}"
        assert response.proposal.operation == "POPULATION_COUNTERFACTUAL"
        
        ledger.append("EVT-3", Actor(type="AI", id="gemini"), "AI_PROPOSAL_RECEIVED", {"proposal": response.proposal.model_dump()})
        
        is_valid, msg = ValidationEngine.validate_proposal(response.proposal, ctx)
        assert is_valid, f"Validation failed: {msg}"
        
        # Test passed
