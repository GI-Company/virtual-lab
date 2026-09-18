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
    """Returns RFC 8785 / JCS-style canonical JSON representation."""
    return json.dumps(asdict(proposal), sort_keys=True, separators=(',', ':')).encode('utf-8')


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
        execute_fn: Callable[[Proposal], Any]
    ) -> Any:
        """
        ACTION requested
              ↓
        proposal hash recomputed
              ↓
        signature valid?
              ↓
        proposal approved?
              ↓
        not expired?
              ↓
        parameters EXACTLY identical?
              ↓
        target EXACTLY identical?
              ↓
        execute
        """
        # 1. Verify signature
        verify_key = nacl.signing.VerifyKey(public_key_bytes)
        proposal_hash = hash_proposal(proposal)
        
        try:
            verify_key.verify(proposal_hash, signature)
        except BadSignatureError:
            raise ValueError("NO_VALID_ED25519_APPROVAL")

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
            if record.target != proposal.target:
                raise ValueError("TARGET_MISMATCH")
            if record.parameters != proposal.parameters:
                raise ValueError("PARAMETERS_MISMATCH")

        # 4. Execute (Fail closed, no mock executors)
        return execute_fn(proposal)
