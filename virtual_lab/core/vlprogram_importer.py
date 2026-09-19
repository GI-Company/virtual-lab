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
from virtual_lab.core.canonical import canonical_json
from virtual_lab.core.trusted_signers import get_signer_status, TrustState

class VLProgramError(Exception):
    pass

def load_vlprogram(program_dir: str) -> dict:
    """
    Loads a .vlprogram directory, verifies its manifest signature, 
    verifies its artifact hashes, and dynamically loads its equations module.
    """
    manifest_path = os.path.join(program_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise VLProgramError(f"manifest.json not found in {program_dir}")
        
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    # Verify signature
    signature_hex = manifest.pop("vlprogram_signature", None)
    public_key_hex = manifest.pop("vlprogram_public_key", None)
    
    if not signature_hex or not public_key_hex:
        raise VLProgramError("No vlprogram_signature or vlprogram_public_key found in manifest")
        
    manifest_bytes = canonical_json(manifest)
    manifest_hash = hashlib.sha256(manifest_bytes).digest()
    
    try:
        verify_key = nacl.signing.VerifyKey(binascii.unhexlify(public_key_hex))
        verify_key.verify(manifest_hash, binascii.unhexlify(signature_hex))
    except BadSignatureError:
        raise VLProgramError(f"Signature mismatch. Signature verification failed.")
    except Exception as e:
        raise VLProgramError(f"Invalid signature format: {e}")
        
    trust_state = get_signer_status(public_key_hex)
    if trust_state != TrustState.TRUSTED:
        raise VLProgramError(f"SIGNATURE_VALID, AUTHENTICITY_{trust_state.value}")
        
    # Verify artifacts
    for artifact_name, expected_hash in manifest.get("artifacts", {}).items():
        artifact_path = os.path.join(program_dir, artifact_name)
        if not os.path.exists(artifact_path):
            raise VLProgramError(f"Artifact {artifact_name} not found")
        with open(artifact_path, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        if actual_hash != expected_hash:
            raise VLProgramError(f"Artifact {artifact_name} hash mismatch")
            
    # Dynamically load the module (for rho_system.py)
    if "rho_system.py" in manifest.get("artifacts", {}):
        system_path = os.path.join(program_dir, "rho_system.py")
        spec = importlib.util.spec_from_file_location("rho_system", system_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manifest["module"] = module
    
    manifest["vlprogram_signature"] = signature_hex
    manifest["vlprogram_public_key"] = public_key_hex
    return manifest

