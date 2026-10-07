"""Prediction bundles, integrity verification, and observation/ledger registration."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from virtual_lab.domain.epistemics import EpistemicState
from virtual_lab.domain.observation import NormalizedObservation, ObservationKind


def data_root() -> Path:
    return Path(os.environ.get("VIRTUALLAB_DATA_DIR", Path.home() / "Library/Application Support/VirtualLab/cockpit"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


@dataclass(frozen=True)
class CompletedRun:
    manifest_path: str
    sha256: str

    def read(self) -> dict:
        path = Path(self.manifest_path)
        if digest(path) != self.sha256:
            raise ValueError("Prediction manifest hash mismatch.")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for artifact in manifest["artifacts"]:
            name = artifact["file"]
            if Path(name).name != name or name in (".", ".."):
                raise ValueError("Invalid artifact path.")
            target = path.parent / name
            if target.is_symlink() or target.stat().st_size != artifact["size_bytes"] or digest(target) != artifact["sha256"]:
                raise ValueError("Prediction artifact integrity check failed.")
        return manifest


def execute(request, adapter, root: Path | None = None) -> CompletedRun:
    """Adapters save raw files; only a complete bundle gets a manifest and final name."""
    import shutil
    root = Path(root) if root is not None else data_root() / "computational"
    root.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    pending = root / (run_id + ".partial")
    pending.mkdir()
    created = datetime.now(timezone.utc).isoformat()
    try:
        details = adapter.execute(request, pending)
        artifacts = [{"file": p.name, "sha256": digest(p), "size_bytes": p.stat().st_size}
                     for p in sorted(pending.iterdir()) if p.is_file()]
        if not artifacts:
            raise ValueError("Instrument produced no artifacts.")
        manifest = {
            "schema_version": 1, "run_id": run_id, "created_at": created,
            "instrument": request.instrument, "epistemic_state": "PREDICTED",
            "request": request.model_dump(mode="json"), "artifacts": artifacts, **details,
        }
        write_json(pending / "manifest.json", manifest)
        final = root / run_id
        pending.rename(final)
        path = final / "manifest.json"
        return CompletedRun(str(path.resolve()), digest(path))
    except BaseException:
        # Only this invocation's fresh temporary directory is removed.
        shutil.rmtree(pending, ignore_errors=True)
        raise


def register(run: CompletedRun, ledger, store) -> NormalizedObservation:
    """Call on the ledger-owning thread. Repeated registration is idempotent."""
    from virtual_lab.core.ledger import Actor
    manifest = run.read()
    observation = NormalizedObservation(
        observation_id=manifest["run_id"], experiment_id=manifest["request"]["experiment_id"],
        session_id=manifest["run_id"], instrument_id=manifest["instrument"],
        kind=(ObservationKind.MODEL_EVALUATION if manifest["instrument"] == "bitvision_simulator_audit"
              else ObservationKind.VIRTUAL_ASSAY), quantities=[],
        artifact_path=run.manifest_path, artifact_sha256=run.sha256,
        acquisition_utc=manifest["created_at"], epistemic_state=EpistemicState(manifest["epistemic_state"]),
        parent_observation_id=manifest.get("parent_run", {}).get("run_id"),
        notes=json.dumps({"hypothesis": manifest["request"]["hypothesis"],
                          "summary": manifest["summary"], "limitations": manifest["limitations"]}),
    )
    event_id = "COMPUTATIONAL-" + manifest["run_id"]
    existing = ledger.conn.execute("SELECT payload_json FROM ledger_events WHERE event_id = ?", (event_id,)).fetchone()
    if existing:
        if json.loads(existing["payload_json"])["artifact_sha256"] != run.sha256:
            raise ValueError("This run already has a different digest in the ledger.")
    else:
        event_type = ("SIMULATOR_AUDIT_RECORDED" if manifest["instrument"] == "bitvision_simulator_audit"
                      else "COMPUTATIONAL_PREDICTION_RECORDED")
        ledger.append(event_id, Actor(type="SYSTEM", id=manifest["instrument"]),
                      event_type,
                      {"run_id": manifest["run_id"], "experiment_id": observation.experiment_id,
                       "artifact_path": run.manifest_path, "artifact_sha256": run.sha256,
                       "instrument": manifest["instrument"], "epistemic_state": manifest["epistemic_state"]})
    # An assigned staged result must never be restaged by registration retries.
    attached = store._conn.execute("SELECT * FROM observations WHERE observation_id=?",
                                   (observation.observation_id,)).fetchone()
    if attached:
        if attached['artifact_sha256'] != run.sha256:
            raise ValueError("Attached result has a different digest.")
        return store._row_to_obs(attached)
    if observation.experiment_id:
        store.save_observation(observation)
    else:
        store.stage_observation(observation)
    return observation
