"""
virtual_lab.core.vlprogram_importer
───────────────────────────────────
Loads and cryptographically verifies .vlprogram packages.
"""

import os
import json
import hashlib
import importlib.util
import binascii
import nacl.signing
from nacl.exceptions import BadSignatureError
from virtual_lab.core.canonical import canonical_json, legacy_canonical_json, strict_json_loads
from virtual_lab.core.trusted_signers import get_signer_status, TrustState, SignerRole, verify_signer_role

class VLProgramError(Exception):
    pass

def load_vlprogram(program_dir: str, *, allow_trusted_code: bool = False) -> dict:
    """
    Loads a .vlprogram directory, verifies its manifest signature, 
    verifies its artifact hashes, and dynamically loads its equations module.
    """
    base_dir = os.path.realpath(program_dir)
    manifest_path = os.path.join(base_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise VLProgramError(f"manifest.json not found in {program_dir}")
        
    with open(manifest_path, 'rb') as f:
        raw = f.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024: raise VLProgramError('Program manifest exceeds 1 MiB.')
    manifest = strict_json_loads(raw)
        
    # Verify signature
    signature_hex = manifest.pop("vlprogram_signature", None)
    public_key_hex = manifest.pop("vlprogram_public_key", None)
    
    if not signature_hex or not public_key_hex:
        raise VLProgramError("No vlprogram_signature or vlprogram_public_key found in manifest")
        
    scheme = manifest.get('canonicalization', 'python-json-v1')
    if scheme not in ('jcs-v1', 'python-json-v1'): raise VLProgramError('Unknown canonicalization.')
    manifest_bytes = canonical_json(manifest) if scheme == 'jcs-v1' else legacy_canonical_json(manifest)
    manifest_hash = hashlib.sha256(manifest_bytes).digest()
    
    try:
        verify_key = nacl.signing.VerifyKey(binascii.unhexlify(public_key_hex))
        verify_key.verify(manifest_hash, binascii.unhexlify(signature_hex))
    except BadSignatureError:
        raise VLProgramError("Signature mismatch. Signature verification failed.")
    except Exception as e:
        raise VLProgramError(f"Invalid signature format: {e}")
        
    trust_state, _ = get_signer_status(public_key_hex)
    if trust_state != TrustState.TRUSTED:
        raise VLProgramError(f"SIGNATURE_VALID, AUTHENTICITY_{trust_state.value}")
    if not verify_signer_role(public_key_hex, SignerRole.PROGRAM_SIGNER):
        raise VLProgramError("SIGNATURE_VALID, UNAUTHORIZED_SIGNER_ROLE")
        
    # Verify artifacts
    for artifact_name, expected_hash in manifest.get("artifacts", {}).items():
        if os.path.isabs(artifact_name) or ".." in artifact_name.replace("\\", "/").split("/"):
            raise VLProgramError(f"Invalid artifact path: {artifact_name}")
        artifact_path = os.path.realpath(os.path.join(base_dir, artifact_name))
        if not artifact_path.startswith(base_dir + os.sep):
            raise VLProgramError(f"Artifact path escapes program directory: {artifact_name}")
        if not os.path.exists(artifact_path):
            raise VLProgramError(f"Artifact {artifact_name} not found")
        with open(artifact_path, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        if actual_hash != expected_hash:
            raise VLProgramError(f"Artifact {artifact_name} hash mismatch")
            
    # Dynamically load the module (for rho_system.py)
    if "rho_system.py" in manifest.get("artifacts", {}):
        if not allow_trusted_code:
            raise VLProgramError("Executable model code requires explicit trusted-code opt-in; signatures do not sandbox code.")
        system_path = os.path.realpath(os.path.join(base_dir, "rho_system.py"))
        spec = importlib.util.spec_from_file_location("rho_system", system_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manifest["module"] = module
    
    manifest["vlprogram_signature"] = signature_hex
    manifest["vlprogram_public_key"] = public_key_hex
    return manifest

