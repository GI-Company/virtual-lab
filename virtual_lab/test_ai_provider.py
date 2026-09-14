import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from virtual_lab.ai.providers import get_provider
from virtual_lab.ai.base import IntelligenceRequest

def test_gemini_structured_output():
    provider = get_provider("gemini")
    
    # Check if keychain has it
    if not provider.test_connection():
        pytest.skip("Gemini provider not configured or connection failed.")
        
    request = IntelligenceRequest(
        system_prompt="You are an expert scientific AI orchestrator.",
        user_prompt="Compare YC-001 and YC-054 [PREDICTED PARAMETERS / INCOMPLETE] across 1000 P23H systems. Vary k_ERAD by a multiplier between 0.5 and 1.5. Return a valid ExperimentProposal.",
        context_hash="mock_hash",
        require_structured_output=True
    )
    
    response = provider.complete(request)
    
    assert response.provider_id == "gemini"
    assert response.proposal is not None
    assert response.proposal.operation == "POPULATION_COUNTERFACTUAL"
    assert response.proposal.ensemble_size == 1000
    assert len(response.proposal.parameter_changes.sweeps) > 0
    assert response.proposal.parameter_changes.sweeps[0].parameter_name.lower() == "k_erad"
