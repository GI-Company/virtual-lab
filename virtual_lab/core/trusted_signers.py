"""
virtual_lab.core.trusted_signers
────────────────────────────────
Registry of trusted Ed25519 signers for .vlprogram and .vlab archives.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List

class TrustState(Enum):
    TRUSTED = "TRUSTED"
    REVOKED = "REVOKED"
    UNKNOWN = "UNKNOWN"

class SignerRole(Enum):
    BUNDLE_PUBLISHER = "BUNDLE_PUBLISHER"
    PROGRAM_SIGNER = "PROGRAM_SIGNER"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"

@dataclass
class TrustedSigner:
    signer_id: str
    public_key_hex: str
    fingerprint: str
    status: TrustState
    permitted_roles: List[SignerRole]
    added_at: str

# In a real environment, this would be loaded from a secure keystore or config.
# For the PoC, we hardcode known signers.
_REGISTRY = {
    # H-1 key for human approvals
    "a4d19f5a5e6a6d57433afd760e2efb5efa44427b7e1f2d642763210196589912": TrustedSigner(
        signer_id="H-1",
        public_key_hex="a4d19f5a5e6a6d57433afd760e2efb5efa44427b7e1f2d642763210196589912",
        fingerprint="sha256:...",
        status=TrustState.TRUSTED,
        permitted_roles=[SignerRole.HUMAN_APPROVAL],
        added_at="2026-09-18T00:00:00Z"
    ),
    # Publisher key for bundle signing
    "414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935": TrustedSigner(
        signer_id="SYSTEM-PUBLISHER",
        public_key_hex="414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935",
        fingerprint="sha256:...",
        status=TrustState.TRUSTED,
        permitted_roles=[SignerRole.BUNDLE_PUBLISHER, SignerRole.PROGRAM_SIGNER],
        added_at="2026-09-18T00:00:00Z"
    )
}

def get_signer(public_key_hex: str) -> Optional[TrustedSigner]:
    return _REGISTRY.get(public_key_hex)

def get_signer_status(public_key_hex: str) -> tuple[TrustState, Optional[str]]:
    signer = _REGISTRY.get(public_key_hex)
    if not signer:
        return TrustState.UNKNOWN, None
    return signer.status, signer.fingerprint

def verify_signer_role(public_key_hex: str, required_role: SignerRole) -> bool:
    signer = _REGISTRY.get(public_key_hex)
    if not signer or signer.status != TrustState.TRUSTED:
        return False
    return required_role in signer.permitted_roles
