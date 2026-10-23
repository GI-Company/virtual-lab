"""
virtual_lab.core.trusted_signers
────────────────────────────────
Registry of trusted Ed25519 signers for .vlprogram and .vlab archives.
"""

from enum import Enum
from dataclasses import dataclass
import hashlib
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

def _fingerprint(public_key_hex: str) -> str:
    return f"sha256:{hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()}"


# In a real environment, this would be loaded from a secure keystore or config.
# For the PoC, we register known demonstration signers.
_REGISTRY = {
    # H-1 key for human approvals
    "a4d19f5a5e6a6d57433afd760e2efb5efa44427b7e1f2d642763210196589912": TrustedSigner(
        signer_id="H-1",
        public_key_hex="a4d19f5a5e6a6d57433afd760e2efb5efa44427b7e1f2d642763210196589912",
        fingerprint=_fingerprint("a4d19f5a5e6a6d57433afd760e2efb5efa44427b7e1f2d642763210196589912"),
        status=TrustState.TRUSTED,
        permitted_roles=[SignerRole.HUMAN_APPROVAL],
        added_at="2026-09-18T00:00:00Z"
    ),
    # Compromised demonstration publisher: private seed was public. Never trust it.
    "414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935": TrustedSigner(
        signer_id="SYSTEM-PUBLISHER",
        public_key_hex="414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935",
        fingerprint=_fingerprint("414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935"),
        status=TrustState.REVOKED,
        permitted_roles=[],
        added_at="2026-09-18T00:00:00Z"
    )
}

def get_signer(public_key_hex: str) -> Optional[TrustedSigner]:
    builtin = _REGISTRY.get(public_key_hex)
    if builtin and builtin.status == TrustState.REVOKED:
        return builtin
    return builtin or _configured_signer(public_key_hex)

def get_signer_status(public_key_hex: str) -> tuple[TrustState, Optional[str]]:
    signer = get_signer(public_key_hex)
    if not signer:
        return TrustState.UNKNOWN, None
    return signer.status, signer.fingerprint

def verify_signer_role(public_key_hex: str, required_role: SignerRole) -> bool:
    signer = get_signer(public_key_hex)
    if not signer or signer.status != TrustState.TRUSTED:
        return False
    return required_role in signer.permitted_roles


def _configured_signer(public_key_hex):
    """Explicit operator trust file. A package can never enroll its own signer."""
    import os
    from pathlib import Path
    from virtual_lab.core.canonical import strict_json_loads
    configured = os.environ.get('VIRTUALLAB_TRUST_STORE')
    if not configured:
        return None
    path = Path(configured).expanduser()
    with path.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Trust store exceeds size limit.')
    document = strict_json_loads(raw)
    if set(document) != {'format', 'signers'} or document['format'] != 'vlab-trust-v1':
        raise ValueError('Unsupported trust-store format.')
    seen = set(); selected = None
    for entry in document['signers']:
        if set(entry) != {'signer_id', 'public_key_hex', 'roles'}:
            raise ValueError('Malformed trust-store signer.')
        public = entry['public_key_hex']
        if len(bytes.fromhex(public)) != 32 or public in seen:
            raise ValueError('Invalid or duplicate signer public key.')
        seen.add(public)
        roles = [SignerRole(role) for role in entry['roles']]
        if not isinstance(entry['signer_id'], str) or not entry['signer_id'].strip():
            raise ValueError('A signer identity is required.')
        if public == public_key_hex:
            selected = TrustedSigner(entry['signer_id'], public, _fingerprint(public),
                TrustState.TRUSTED, roles, 'operator-configured')
    return selected
