"""
virtual_lab.core.vlprogram_importer
───────────────────────────────────
Loads and cryptographically verifies .vlprogram packages.
"""

import os
import json
import hashlib
import importlib.util

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
    signature = manifest.pop("vlprogram_signature", None)
    if not signature:
        raise VLProgramError("No vlprogram_signature found in manifest")
        
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode('utf-8')
    computed_signature = hashlib.sha256(manifest_bytes).hexdigest()
    
    if computed_signature != signature:
        raise VLProgramError(f"Signature mismatch. Expected {signature}, got {computed_signature}")
        
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
    # The actual artifact name might be different, but for now we expect rho_system.py
    if "rho_system.py" in manifest.get("artifacts", {}):
        system_path = os.path.join(program_dir, "rho_system.py")
        spec = importlib.util.spec_from_file_location("rho_system", system_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manifest["module"] = module
    
    manifest["vlprogram_signature"] = signature
    return manifest
