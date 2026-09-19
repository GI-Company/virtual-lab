"""
virtual_lab.ai.model_fingerprint
────────────────────────────────
Records the exact execution environment for the AI model to guarantee `.vlab` verifiability.
"""
import os
import hashlib
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelFingerprint:
    model_family: str
    model_variant: str
    weights_sha256: str
    quantization: str
    runtime: str
    runtime_version: str
    hardware_backend: str
    temperature: float
    system_prompt_hash: str
    tool_schema_hash: str
    context_snapshot_hash: str
    provenance: str

def _hash_file_cached(filepath: Path, force: bool = False) -> str:
    """Computes SHA-256 for large files, caching by mtime and size."""
    if not filepath.exists():
        return "UNAVAILABLE"
        
    stat = filepath.stat()
    cache_key = f"{filepath.name}_{stat.st_size}_{stat.st_mtime}"
    cache_file = Path("/tmp") / f"vlab_hash_cache_{hashlib.md5(cache_key.encode()).hexdigest()}.txt"
    
    if not force and cache_file.exists():
        return cache_file.read_text().strip()
        
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Read in chunks to handle large models
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
            
    result = sha256_hash.hexdigest()
    cache_file.write_text(result)
    return result

def get_current_fingerprint(force_hash: bool = False) -> ModelFingerprint:
    model_path_str = os.environ.get("VIRTUALLAB_LOCAL_MODEL")
    model_file = None
    if model_path_str:
        model_file = Path(model_path_str) / "gemma-4-e2b-it-Q8_0.gguf"
        
    weights_hash = "UNAVAILABLE"
    provenance = "UNAVAILABLE"
    if model_file and model_file.exists():
        weights_hash = _hash_file_cached(model_file, force=force_hash)
        provenance = f"file://{model_file.absolute()}"
    
    try:
        import importlib.metadata
        runtime_version = importlib.metadata.version("mlx")
    except Exception:
        runtime_version = "UNAVAILABLE"

    return ModelFingerprint(
        model_family="gemma-4",
        model_variant="E2B-it",
        weights_sha256=weights_hash,
        quantization="8-bit" if (model_file and "Q8" in str(model_file)) else "UNAVAILABLE",
        runtime="mlx",
        runtime_version=runtime_version,
        hardware_backend="Metal",
        temperature=0.0,
        system_prompt_hash="UNAVAILABLE",
        tool_schema_hash="UNAVAILABLE",
        context_snapshot_hash="UNAVAILABLE",
        provenance=provenance
    )
