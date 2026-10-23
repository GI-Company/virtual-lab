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
    canonicalization: str = "jcs-v1"

def get_canonical_json(proposal: Proposal) -> bytes:
    """Returns RFC 8785 / JCS-style canonical JSON representation using central library."""
    return canonical_json(asdict(proposal))

def hash_proposal(proposal: Proposal) -> bytes:
    return hashlib.sha256(get_canonical_json(proposal)).digest()

def _parse_iso_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError('Timezone required for approval timestamps')
    return dt.astimezone(timezone.utc)


class ApprovalPolicy:
    """Enforces cryptographic approval for actions before execution."""
    
    def __init__(self, genesis_ledger=None):
        self.genesis_ledger = genesis_ledger
        self._executed_keys: set[tuple[str, str]] = set()

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
        if self.genesis_ledger is None or self.genesis_ledger.db_path == ':memory:':
            raise ValueError('DURABLE_LEDGER_REQUIRED')
        if proposal.canonicalization != 'jcs-v1' or not proposal.proposal_id or not proposal.nonce:
            raise ValueError('INVALID_PROPOSAL_IDENTITY_OR_CANONICALIZATION')
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

        # 2. Check expiration and replay
        now = datetime.now(timezone.utc)
        expires_at = _parse_iso_utc(proposal.expires_at)
        issued_at = _parse_iso_utc(proposal.issued_at)
        if issued_at > now or expires_at <= issued_at:
            raise ValueError('INVALID_APPROVAL_TIME_WINDOW')
        if now >= expires_at:
            raise ValueError("APPROVAL_EXPIRED")

        replay_key = (proposal.proposal_id, proposal.nonce)
        if replay_key in self._executed_keys:
            raise ValueError("PROPOSAL_ALREADY_EXECUTED")

        # 3. Genesis verification
        if self.genesis_ledger:
            record = self.genesis_ledger.get_approval_record(proposal.proposal_id)
            if not record:
                raise ValueError("APPROVAL_NOT_FOUND_IN_GENESIS")
                
            for field, expected in asdict(proposal).items():
                if field not in record or record[field] != expected:
                    raise ValueError('PROPOSAL_FIELD_MISMATCH: ' + field)
            # Target, action_type, and parameters EXACTLY identical to the immutable ledger record
            if record.get("target") != proposal.target:
                raise ValueError("TARGET_MISMATCH")
            if "action_type" in record and record.get("action_type") != proposal.action_type:
                raise ValueError("ACTION_TYPE_MISMATCH")
            if record.get("parameters") != proposal.parameters:
                raise ValueError("PARAMETERS_MISMATCH")
                
            # Check for HUMAN_DECISION event for this proposal and ensure it hasn't already executed
            events = self.genesis_ledger.get_events_by_proposal(proposal.proposal_id)
            if not any(evt.event_type == 'RULE_EVALUATION' and evt.payload.get('passed') is True for evt in events):
                raise ValueError('PROPOSAL_RULE_CHECK_NOT_PASSED')
            approved = False
            for evt in events:
                if evt.event_type == "ACTION_EXECUTED":
                    raise ValueError("PROPOSAL_ALREADY_EXECUTED")
                if evt.event_type == "HUMAN_DECISION" and evt.payload.get("decision") == "APPROVED":
                    recorded_sig = evt.payload.get("signature")
                    if recorded_sig != signature.hex() or evt.actor.id != signer.signer_id:
                        raise ValueError("SIGNATURE_MISMATCH_IN_GENESIS")
                    approved = True
            if not approved:
                raise ValueError("PROPOSAL_NOT_APPROVED_IN_GENESIS")

        self.genesis_ledger.claim_execution(proposal.proposal_id, proposal.nonce,
            signer.signer_id, proposal_hash.hex())
        # The durable claim remains consumed even if this callback fails or crashes.
        try:
            result = execute_fn(proposal)
        except BaseException as exc:
            from virtual_lab.core.ledger import Actor
            import uuid
            self.genesis_ledger.append('FAILED_' + uuid.uuid4().hex,
                Actor(type='HUMAN', id=signer.signer_id), 'ACTION_FAILED',
                {'proposal_id': proposal.proposal_id, 'nonce': proposal.nonce,
                 'error_type': type(exc).__name__, 'reconciliation_required': True})
            raise
        self._executed_keys.add(replay_key)
        if self.genesis_ledger:
            from virtual_lab.core.ledger import Actor
            import uuid
            self.genesis_ledger.append(
                f"EXEC_{proposal.proposal_id}_{uuid.uuid4().hex[:8]}",
                Actor(type="HUMAN", id=signer.signer_id),
                "ACTION_EXECUTED",
                {"proposal_id": proposal.proposal_id, "nonce": proposal.nonce, "action_type": proposal.action_type},
            )
        return result

