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
    import nacl.signing
    key_hex = os.environ.get('VLAB_PUBLISHER_SK')
    if not key_hex:
        raise ValueError('VLAB_PUBLISHER_SK must explicitly supply a private signing key.')
    try:
        signing_key = nacl.signing.SigningKey(bytes.fromhex(key_hex))
    except (ValueError, TypeError):
        raise ValueError('Publisher key must be a 32-byte Ed25519 seed in hex.') from None
    from virtual_lab.core.trusted_signers import get_signer_status, TrustState
    if get_signer_status(signing_key.verify_key.encode().hex())[0] == TrustState.REVOKED:
        raise ValueError('The compromised demonstration publisher key is revoked.')
    if not os.path.exists(experiment_dir):
        raise ValueError(f"Experiment directory not found: {experiment_dir}")
        
    genesis_path = os.path.join(experiment_dir, "genesis.db")
    if not os.path.exists(genesis_path):
        print("Warning: No genesis.db found in experiment directory.")
        
    # Snapshot SQLite through its backup API, including committed WAL records.
    # Build outside the source tree and replace only after successful completion.
    import sqlite3
    import tempfile
    from pathlib import Path
    source = Path(experiment_dir).resolve()
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "vlab_version": "2.0", "canonicalization": "jcs-v1",
        "publisher_public_key": signing_key.verify_key.encode().hex(),
        "build_utc": datetime.now(timezone.utc).isoformat(), "contents": []}
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        package = temporary / 'bundle.zip'
        with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for root, dirs, files in os.walk(source, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and
                    d not in ('build', '__pycache__') and not (Path(root)/d).is_symlink())
                for name in sorted(files):
                    path = Path(root) / name
                    if path.resolve() == output or name.startswith('.') or name.endswith(('-wal', '-shm')):
                        continue
                    if path.is_symlink():
                        raise ValueError('Symlinks cannot be bundled.')
                    if path == Path(genesis_path).resolve():
                        snapshot = temporary / 'genesis.db'
                        original = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
                        copy = sqlite3.connect(snapshot)
                        try:
                            original.backup(copy)
                        finally:
                            copy.close(); original.close()
                        data = snapshot.read_bytes()
                    else:
                        data = path.read_bytes()
                    relative = path.relative_to(source).as_posix()
                    manifest['contents'].append({'path': relative, 'sha256': hashlib.sha256(data).hexdigest()})
                    bundle.writestr(relative, data)
            from virtual_lab.core.canonical import canonical_json
            encoded = canonical_json(manifest)
            bundle.writestr('manifest.json', encoded)
            bundle.writestr('manifest.sig', signing_key.sign(encoded).signature)
        # Stage on the destination filesystem for atomic replacement.
        import shutil
        handle, staged = tempfile.mkstemp(prefix='.vlab-bundle-', dir=output.parent)
        try:
            with os.fdopen(handle, 'wb') as stream, package.open('rb') as data:
                shutil.copyfileobj(data, stream)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(staged, output)
        finally:
            if os.path.exists(staged): os.unlink(staged)
    print(f"Successfully built .vlab bundle at {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a .vlab bundle.")
    parser.add_argument("experiment_dir", help="Path to the experiment directory.")
    parser.add_argument("output_path", help="Path to write the .vlab file.")
    args = parser.parse_args()
    build_vlab_bundle(args.experiment_dir, args.output_path)
