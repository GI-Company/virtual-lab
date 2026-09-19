"""
virtual_lab.domain.approval_policy
──────────────────────────────────
Cryptographic human-in-the-loop approval using Ed25519.
Binds approvals to a canonical proposal hash.
Execution fails closed. No mock executors or fallbacks allowed.
"""

import json
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Callable
import nacl.signing
from nacl.exceptions import BadSignatureError
from virtual_lab.core.canonical import canonical_json
from virtual_lab.core.trusted_signers import get_signer_status, get_signer, TrustState

@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    action_type: str
    parameters: Dict[str, Any]
    target: str
    actor_id: str
    issued_at: str
    expires_at: str
    nonce: str

def get_canonical_json(proposal: Proposal) -> bytes:
    """Returns RFC 8785 / JCS-style canonical JSON representation using central library."""
    return canonical_json(asdict(proposal))

def hash_proposal(proposal: Proposal) -> bytes:
    return hashlib.sha256(get_canonical_json(proposal)).digest()

class ApprovalPolicy:
    """Enforces cryptographic approval for actions before execution."""
    
    def __init__(self, genesis_ledger=None):
        self.genesis_ledger = genesis_ledger

    def sign_proposal(self, proposal: Proposal, signing_key: nacl.signing.SigningKey) -> bytes:
        """Sign the SHA256 hash of the canonical proposal."""
        proposal_hash = hash_proposal(proposal)
        signed = signing_key.sign(proposal_hash)
        return signed.signature

    def verify_and_execute(
        self,
        proposal: Proposal,
        signature: bytes,
        public_key_bytes: bytes,
        execute_fn: Callable[[Proposal], Any],
        human_actor_id: Optional[str] = None
    ) -> Any:
        # 1. Verify signature
        verify_key = nacl.signing.VerifyKey(public_key_bytes)
        proposal_hash = hash_proposal(proposal)
        
        try:
            verify_key.verify(proposal_hash, signature)
        except BadSignatureError:
            raise ValueError("NO_VALID_ED25519_APPROVAL")
            
        # 1b. Verify trusted signer identity
        pk_hex = public_key_bytes.hex()
        from virtual_lab.core.trusted_signers import get_signer_status, get_signer, TrustState, SignerRole, verify_signer_role
        
        status, fingerprint = get_signer_status(pk_hex)
        if status != TrustState.TRUSTED:
            raise ValueError(f"UNTRUSTED_SIGNER: Signer state is {status}")
            
        if not verify_signer_role(pk_hex, SignerRole.HUMAN_APPROVAL):
            raise ValueError("UNAUTHORIZED_ROLE: Signer does not have HUMAN_APPROVAL role")
            
        signer = get_signer(pk_hex)
        if not signer:
            raise ValueError("UNKNOWN_SIGNER")
            
        if human_actor_id and signer.signer_id != human_actor_id:
            raise ValueError(f"SIGNER_MISMATCH: Expected {human_actor_id}, got {signer.signer_id}")

        # 2. Check expiration
        now = datetime.now(timezone.utc).isoformat()
        if now > proposal.expires_at:
            raise ValueError("APPROVAL_EXPIRED")

        # 3. Genesis verification
        if self.genesis_ledger:
            record = self.genesis_ledger.get_approval_record(proposal.proposal_id)
            if not record:
                raise ValueError("APPROVAL_NOT_FOUND_IN_GENESIS")
                
            # Target and parameters EXACTLY identical to the immutable ledger record
            if record.get("target") != proposal.target:
                raise ValueError("TARGET_MISMATCH")
            if record.get("parameters") != proposal.parameters:
                raise ValueError("PARAMETERS_MISMATCH")
                
            # Check for HUMAN_DECISION event for this proposal to ensure it was approved
            events = self.genesis_ledger.get_events_by_proposal(proposal.proposal_id)
            approved = False
            for evt in events:
                if evt.event_type == "HUMAN_DECISION" and evt.payload.get("decision") == "APPROVED":
                    approved = True
            if not approved:
                raise ValueError("PROPOSAL_NOT_APPROVED_IN_GENESIS")

        # 4. Execute (Fail closed, no mock executors)
        return execute_fn(proposal)

