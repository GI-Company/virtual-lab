import pytest
from virtual_lab.ai.tools import AGENT_TOOLS
from virtual_lab.ai.epistemic_identity import wrap_ai_proposal
from virtual_lab.core.ledger import GenesisLedger, Actor
from virtual_lab.domain.approval_policy import ApprovalPolicy, Proposal
from datetime import datetime, timezone

def test_l1_autonomy_tool_surface():
    """Verify the AI has ZERO execution tools available."""
    tool_names = [func.__name__ for func in AGENT_TOOLS]
    
    # Assert restricted verbs
    for forbidden in ["execute", "set", "write", "approve", "mark_valid"]:
        for tool in tool_names:
            assert forbidden not in tool, f"Adversarial Failure: Found execution verb {tool}"
            
def test_epistemic_identity_wrapper():
    """Verify AI outputs are strictly wrapped as INFERRED."""
    raw_output = {"hypothesis": "The sky is green"}
    wrapped = wrap_ai_proposal(raw_output)
    
    assert wrapped["identity"]["epistemic_state"] == "INFERRED"
    assert wrapped["identity"]["authoritative"] is False
    assert wrapped["payload"] == raw_output
    
def test_cryptographic_execution_rejection():
    """Verify that an AI cannot execute an action without a valid Ed25519 signature."""
    policy = ApprovalPolicy()
    
    proposal = Proposal(
        proposal_id="fake_id",
        action_type="POPULATION_COUNTERFACTUAL",
        parameters={"dose": 1.0},
        target="RHO_P23H",
        actor_id="gemma_4",
        issued_at=datetime.now(timezone.utc).isoformat(),
        expires_at=datetime.now(timezone.utc).isoformat(),
        nonce="1234"
    )
    
    fake_signature = b"0" * 64
    fake_public_key = b"0" * 32
    
    with pytest.raises(ValueError, match="NO_VALID_ED25519_APPROVAL"):
        policy.verify_and_execute(proposal, fake_signature, fake_public_key, lambda x: True)
