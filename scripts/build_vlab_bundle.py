import os
import zipfile
import json
import hashlib
from datetime import datetime, timezone
import argparse

def build_vlab_bundle(experiment_dir: str, output_path: str):
    """
    Packages an experiment workspace into an immutable .vlab cryptographic bundle.
    """
    if not os.path.exists(experiment_dir):
        raise ValueError(f"Experiment directory not found: {experiment_dir}")
        
    genesis_path = os.path.join(experiment_dir, "genesis.db")
    if not os.path.exists(genesis_path):
        print("Warning: No genesis.db found in experiment directory.")
        
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as bundle:
        manifest = {
            "vlab_version": "1.0",
            "build_utc": datetime.now(timezone.utc).isoformat(),
            "contents": []
        }
        # Write genesis.db and its hash
        if os.path.exists(genesis_path):
            bundle.write(genesis_path, "genesis.db")
            with open(genesis_path, 'rb') as f:
                genesis_hash = hashlib.sha256(f.read()).hexdigest()
            manifest["contents"].append({
                "path": "genesis.db",
                "sha256": genesis_hash
            })
            
        for root, dirs, files in os.walk(experiment_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('build', '__pycache__')]
            for file in files:
                if file == "genesis.db" or file.startswith('.'):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, experiment_dir)
                
                with open(file_path, 'rb') as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                    
                manifest["contents"].append({
                    "path": rel_path,
                    "sha256": file_hash
                })
                bundle.write(file_path, rel_path)
                
        # Write manifest
        from virtual_lab.core.canonical import canonical_json
        import nacl.signing
        import binascii
        
        # Use a real Ed25519 publisher key for the PoC
        VLAB_PUBLISHER_SK = os.environ.get("VLAB_PUBLISHER_SK", "78295015b6748f63b2d0c9822e82842e650b1404649c0556dfefd6b84ed3abfc")
        signing_key = nacl.signing.SigningKey(binascii.unhexlify(VLAB_PUBLISHER_SK))
        
        manifest_bytes = canonical_json(manifest)
        bundle.writestr("manifest.json", manifest_bytes)
        
        # Create detached signature
        signature = signing_key.sign(manifest_bytes).signature
        bundle.writestr("manifest.sig", signature)
        
    print(f"Successfully built .vlab bundle at {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a .vlab bundle.")
    parser.add_argument("experiment_dir", help="Path to the experiment directory.")
    parser.add_argument("output_path", help="Path to write the .vlab file.")
    args = parser.parse_args()
    build_vlab_bundle(args.experiment_dir, args.output_path)
