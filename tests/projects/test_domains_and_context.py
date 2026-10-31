"""Domain metadata never rewrites scientific evidence; view references stay scoped."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import zipfile
import pytest
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.domain.research_domains import (
    DOMAINS,
    TOOLS,
    Availability,
    tool_availability,
)
from virtual_lab.gui.services.study_service import StudyService
from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.pilots.datasets import MSDatasetService
from virtual_lab.pilots.lease import WorkspaceLease


@pytest.fixture
def study(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(tmp_path))
    lease = WorkspaceLease(tmp_path)
    ledger = GenesisLedger(str(tmp_path / "genesis.db"))
    store = ExperimentStore(str(tmp_path / "experiments.db"))
    service = StudyService(WorkspaceState(), ledger, store)
    yield service, lease, tmp_path
    store.close()
    ledger.conn.close()
    lease.close()


def add_scan(study, experiment_id, name="scan", mz=100):
    svc, lease, root = study
    source = root / (name + ".csv")
    source.write_text(f"mz,intensity\n{mz},12\n{mz+1},6\n")
    ms = MSDatasetService(svc.ledger, svc.store, root / "ms-pilot-runs", lease=lease)
    return ms.import_csv(
        source,
        experiment_id=experiment_id,
        dataset_id=name,
        sample_id="synthetic",
        instrument_id="synthetic",
        operator_id="test",
        approved_nonconfidential=True,
        data_origin="synthetic",
    )


def test_registry_exposes_real_status_and_absence():
    assert len(DOMAINS) == 7
    assert TOOLS["intent"].status == Availability.EXPERIMENTAL
    assert tool_availability("ms_workflow", {"ms_workflow"}) == Availability.ENABLED
    assert tool_availability("simulation", {"ms_workflow"}) == Availability.UNAVAILABLE
    assert tool_availability("ms_identification", set()) == Availability.UNAVAILABLE


def test_additive_legacy_migration_preserves_evidence_and_private_backup(study):
    svc, lease, root = study
    project = svc.create_project("Legacy")
    exp = svc.create_experiment(project, "Original", "Preserve the same evidence?")
    obs = add_scan(study, exp)
    raw = Path(obs.artifact_path).read_bytes()
    before = dict(svc.store._conn.execute("SELECT * FROM observations").fetchone())
    chain = [tuple(r) for r in svc.ledger.conn.execute("SELECT * FROM ledger_events")]
    svc.store.close()
    with sqlite3.connect(root / "experiments.db") as legacy:
        legacy.execute("ALTER TABLE projects DROP COLUMN domain_id")
        legacy.execute("DROP TABLE project_context")
        legacy.execute("DROP TABLE experiment_context")
    svc.store = ExperimentStore(str(root / "experiments.db"))
    assert (
        svc.projects()[0]["id"] == project
        and svc.projects()[0]["domain_id"] == "general"
    )
    assert svc.store.get_experiment(exp)["project_id"] == project
    assert (
        dict(svc.store._conn.execute("SELECT * FROM observations").fetchone()) == before
    )
    assert Path(obs.artifact_path).read_bytes() == raw
    assert [
        tuple(r) for r in svc.ledger.conn.execute("SELECT * FROM ledger_events")
    ] == chain
    backups = list(root.glob("experiments-pre-domain-v1-*.sqlite3"))
    assert len(backups) == 1
    if os.name != "nt":
        assert backups[0].stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(backups[0]) as backup:
        assert "domain_id" not in {
            r[1] for r in backup.execute("PRAGMA table_info(projects)")
        }
        assert (
            backup.execute("SELECT artifact_sha256 FROM observations").fetchone()[0]
            == obs.artifact_sha256
        )


def test_domain_move_and_failure_leave_ids_and_measurements_intact(study, monkeypatch):
    svc, _, _ = study
    project = svc.create_project("Move", "mass_spectrometry")
    exp = svc.create_experiment(project, "First", "Question")
    obs = add_scan(study, exp)
    before = Path(obs.artifact_path).read_bytes()
    svc.set_project_domain(project, "data_analysis")
    assert svc.projects()[0]["domain_id"] == "data_analysis"
    assert svc.store.get_experiment(exp)["project_id"] == project
    assert Path(obs.artifact_path).read_bytes() == before

    def fail(*_):
        raise OSError("ledger unavailable")

    monkeypatch.setattr(svc, "_event", fail)
    with pytest.raises(OSError):
        svc.set_project_domain(project, "physics_simulation")
    assert svc.projects()[0]["domain_id"] == "data_analysis"
    with pytest.raises(ValueError):
        svc.create_project("Invalid", "imaginary")


def test_context_references_reject_foreign_datasets_and_stale_experiments(study):
    svc, _, _ = study
    p = svc.create_project("A", "mass_spectrometry")
    a = svc.create_experiment(p, "A", "Question")
    scan = add_scan(study, a)
    q = svc.create_project("B", "mass_spectrometry")
    b = svc.create_experiment(q, "B", "Question")
    with pytest.raises(ValueError, match="belong"):
        svc.save_experiment_view(b, selected_ms_run_id=scan.session_id)
    with pytest.raises(ValueError, match="belong"):
        svc.save_experiment_view(b, selected_observation_id=scan.observation_id)
    with svc.store._conn:
        svc.store._conn.execute(
            "UPDATE project_context SET last_experiment_id=? WHERE project_id=?", (b, p)
        )
    svc.open_project(p)
    assert svc.workspace.active_experiment.id == a
    with svc.store._conn:
        svc.store._conn.execute(
            "INSERT OR REPLACE INTO experiment_context (experiment_id,ms_tab_id,notebook_tab_id) VALUES (?,?,?)",
            (a, "future-view", "future-view"),
        )
    assert svc.experiment_view(a)["ms_tab_id"] == "import"
    assert svc.experiment_view(a)["notebook_tab_id"] == "details"
    with pytest.raises(ValueError):
        svc.save_experiment_view(a, ms_tab_id="future-view")


@pytest.mark.parametrize("legacy", [False, True])
def test_domain_study_roundtrip_and_old_package_compatibility(
    study, tmp_path, monkeypatch, legacy
):
    svc, _, root = study
    p = svc.create_project("Portable", "mass_spectrometry")
    exp = svc.create_experiment(p, "Scan", "Question")
    obs = add_scan(study, exp)
    package = svc.export_study(root / "source.vlab-study")
    if legacy:
        with zipfile.ZipFile(package) as z:
            files = {n: z.read(n) for n in z.namelist()}
        snapshot = json.loads(files["study.json"])
        snapshot["project"].pop("domain_id")
        files["study.json"] = json.dumps(snapshot).encode()
        package = root / "legacy.vlab-study"
        with zipfile.ZipFile(package, "w") as z:
            for name, raw in files.items():
                z.writestr(name, raw)
    target = root / "recipient"
    target.mkdir()
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(target))
    ledger = GenesisLedger(str(target / "genesis.db"))
    store = ExperimentStore(str(target / "experiments.db"))
    try:
        recipient = StudyService(WorkspaceState(), ledger, store)
        recipient.import_study(package)
        assert recipient.projects()[0]["domain_id"] == (
            "general" if legacy else "mass_spectrometry"
        )
        assert recipient.workspace.active_experiment.id == exp
        assert (
            recipient.store.get_observations_for_experiment(exp)[0].artifact_sha256
            == obs.artifact_sha256
        )
        assert not recipient.experiment_view(exp).get("selected_ms_run_id")
        assert not recipient.project_context(p).get("last_tool_id") == "instruments"
    finally:
        store.close()
        ledger.conn.close()


def test_search_and_recent_projects_follow_explicit_opens(study):
    svc, _, _ = study
    a = svc.create_project("Alpha study", "mass_spectrometry")
    b = svc.create_project("Beta study", "data_analysis")
    svc.open_project(a)
    svc.open_project(b)
    svc.open_project(a)
    assert [p["id"] for p in svc.projects(recent=True)] == [a, b]
    assert [p["id"] for p in svc.projects("mass_spectrometry", "ALPHA")] == [a]
    assert not svc.projects("mass_spectrometry", "Beta")
