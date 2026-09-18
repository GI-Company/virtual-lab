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
        # Add core ledger
        if os.path.exists(genesis_path):
            bundle.write(genesis_path, "genesis.db")
            
        # Add any raw data or parameters found in the directory
        manifest = {
            "vlab_version": "1.0",
            "build_utc": datetime.now(timezone.utc).isoformat(),
            "contents": []
        }
        
        for root, _, files in os.walk(experiment_dir):
            for file in files:
                if file == "genesis.db":
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
        manifest_bytes = json.dumps(manifest, indent=2).encode('utf-8')
        bundle.writestr("manifest.json", manifest_bytes)
        
    print(f"Successfully built .vlab bundle at {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a .vlab bundle.")
    parser.add_argument("experiment_dir", help="Path to the experiment directory.")
    parser.add_argument("output_path", help="Path to write the .vlab file.")
    args = parser.parse_args()
    build_vlab_bundle(args.experiment_dir, args.output_path)
