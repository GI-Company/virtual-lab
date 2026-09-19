import os
import json
import hashlib
import shutil
import binascii
import nacl.signing
from virtual_lab.core.canonical import canonical_json

def package_vlprogram(source_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Copy processes.py to rho_system.py
    system_path = os.path.join(output_dir, "rho_system.py")
    shutil.copy(os.path.join(source_dir, "processes.py"), system_path)
    
    with open(system_path, "rb") as f:
        rho_system_hash = hashlib.sha256(f.read()).hexdigest()
        
    manifest = {
        "format": "vlprogram_1.0",
        "program_id": "rho_p23h",
        "state_schema": ["R_f", "R_ER", "R_s", "S", "V"],
        "initial_state": {
            "P23H_UNTREATED": [0.1, 0.8, 0.05, 0.5, 0.8],
            "REFERENCE_HEALTHY": [0.8, 0.1, 0.8, 0.05, 1.0]
        },
        "overrides_schema": {
            "k_syn": "float",
            "k_mis": "float",
            "k_traffic": "float",
            "k_ERAD": "float",
            "k_deg_f": "float",
            "k_deg_s": "float",
            "k_internalize": "float",
            "k_stress": "float",
            "k_recover": "float",
            "k_repair": "float",
            "k_death": "float",
            "rescue_max": "float",
            "ec50": "float",
            "hill_h": "float"
        },
        "artifacts": {
            "rho_system.py": rho_system_hash
        }
    }
    
    # Sign manifest
    manifest_bytes = canonical_json(manifest)
    manifest_hash = hashlib.sha256(manifest_bytes).digest()
    
    sk_hex = os.environ.get("VLAB_PACKAGER_SK")
    if not sk_hex:
        raise ValueError("VLAB_PACKAGER_SK environment variable is required to sign .vlprogram manifests.")
    signing_key = nacl.signing.SigningKey(binascii.unhexlify(sk_hex))
    
    signed = signing_key.sign(manifest_hash)
    signature_hex = binascii.hexlify(signed.signature).decode()
    pk_hex = binascii.hexlify(signing_key.verify_key.encode()).decode()
    
    manifest["vlprogram_signature"] = signature_hex
    manifest["vlprogram_public_key"] = pk_hex
    
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Packaged {output_dir}")
    print(f"Signature: {signature_hex}")

if __name__ == "__main__":
    src = "/Users/hanna/research/VirtualLab/virtual_lab/diseases/rho_p23h"
    out = "/Users/hanna/research/VirtualLab/virtual_lab/diseases/rho_p23h.vlprogram"
    package_vlprogram(src, out)

