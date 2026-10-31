from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import uuid
import pytest
from nacl.signing import SigningKey
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.core.trusted_signers import (
    _REGISTRY,
    TrustedSigner,
    SignerRole,
    TrustState,
)
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.domain.observation import (
    RawObservation,
    NormalizedObservation,
    ObservationKind,
)
from virtual_lab.domain.epistemics import EpistemicState, QualityState
from virtual_lab.intent.controller import IntentController
from virtual_lab.intent.model import MiniModel, canonical
from virtual_lab.intent.schema import FeaturesPolicy, IntentError
from virtual_lab.pilots.lease import WorkspaceLease

SCHEMA = {
    "schema_id": "software-fixture-outcome-v1",
    "description": "Synthetic software test target, not laboratory validation",
    "features": [{"name": "condition", "unit": "fixture units"}],
    "outcome_name": "fixture measurement",
    "outcome_unit": "fixture units",
}


@pytest.fixture
def context(tmp_path, monkeypatch):
    lease = WorkspaceLease(tmp_path)
    ledger = GenesisLedger(str(tmp_path / "genesis.db"))
    store = ExperimentStore(str(tmp_path / "experiments.db"))
    store._conn.execute("INSERT INTO projects (id,name,created_at) VALUES ('p','test project','now')")
    store._conn.commit()
    key = SigningKey.generate()
    pk = key.verify_key.encode().hex()
    monkeypatch.setitem(
        _REGISTRY,
        pk,
        TrustedSigner(
            "test-reviewer",
            pk,
            "test-only",
            TrustState.TRUSTED,
            [SignerRole.HUMAN_APPROVAL],
            "now",
        ),
    )
    controller = IntentController(ledger, store, tmp_path / "intent", lease=lease)
    model = controller.initialize("p", SCHEMA)
    yield controller, model, key, tmp_path
    store.close()
    ledger.conn.close()
    lease.close()


def prediction(ctx, x=0.0, group=None):
    c, m, _, _ = ctx
    exp = str(uuid.uuid4())
    group = group or exp
    c.store.save_experiment(exp, "", "", "", project_id="p")
    return c.predict(m, exp, {"condition": x}, group)


def measured(
    ctx, pred, y=0.7, purpose="train", state="MEASURED", group=None, acquired=None
):
    c, m, key, root = ctx
    p = pred["payload"]
    obsid = str(uuid.uuid4())
    acquired = acquired or datetime.now(timezone.utc).isoformat()
    data = {
        "format": "intent-measured-outcome-v1",
        "experiment_id": p["experiment_id"],
        "schema_sha256": p["schema_sha256"],
        "group_id": group or p["group_id"],
        "value": float(y),
        "unit": "fixture units",
        "acquired_at_utc": acquired,
    }
    path = root / (obsid + ".json")
    path.write_bytes(canonical(data))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    common = dict(
        observation_id=obsid,
        experiment_id=p["experiment_id"],
        session_id="test-only",
        instrument_id="test-fixture",
        kind=ObservationKind.VIRTUAL_ASSAY,
        quantities=[],
        artifact_path=str(path),
        artifact_sha256=sha,
        acquisition_utc=acquired,
        quality_state=QualityState.VALID,
    )
    obs = (
        RawObservation(**common)
        if state == "MEASURED"
        else NormalizedObservation(**common, epistemic_state=EpistemicState(state))
    )
    c.store.save_observation(obs)
    review = {
        "format": "intent-training-review-v1",
        "model_id": m,
        "project_id": "p",
        "experiment_id": p["experiment_id"],
        "prediction_id": pred["event_id"],
        "observation_id": obsid,
        "artifact_sha256": sha,
        "schema_sha256": p["schema_sha256"],
        "group_id": p["group_id"],
        "purpose": purpose,
        "permitted_data_use": True,
        "reviewer_id": "test-reviewer",
        "expires_at_utc": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    token = {
        "review": review,
        "public_key": key.verify_key.encode().hex(),
        "signature": key.sign(canonical(review)).signature.hex(),
    }
    return obs, token


def accepted(ctx, x=0.0, y=0.7, purpose="train", group=None):
    pred = prediction(ctx, x, group)
    obs, token = measured(ctx, pred, y, purpose)
    return ctx[0].accept_outcome(
        ctx[1], pred["payload"]["experiment_id"], obs.observation_id, token
    )


def enable(ctx, learning=True):
    ctx[0].set_policy(
        {
            "predictions_enabled": True,
            "learning_enabled": learning,
            "training_projects": ["p"],
        }
    )


def freeze(ctx):
    ids = [
        accepted(ctx, x=float(x), y=0.15 if x < 0 else 0.85, purpose="holdout")[
            "event_id"
        ]
        for x in (-4, -2, 1, 3, 5)
    ]
    return ctx[0].freeze_holdout(ctx[1], ids)


def test_default_off_and_separate_prediction_learning_controls(context):
    c, m, _, _ = context
    assert not c.policy().predictions_enabled and not c.policy().learning_enabled
    with pytest.raises(IntentError, match="disabled"):
        prediction(context)
    enable(context, learning=False)
    pred = prediction(context)
    assert (
        pred["payload"]["epistemic_state"] == "PREDICTED"
        and pred["payload"]["uncertainty"] is None
    )
    out = accepted(context)
    with pytest.raises(IntentError, match="disabled"):
        c.prepare_update(m, out["event_id"])


@pytest.mark.parametrize("state", ["UNKNOWN", "PREDICTED", "SIMULATED", "CALCULATED"])
def test_nonmeasurement_evidence_never_trains(context, state):
    enable(context)
    pred = prediction(context)
    obs, token = measured(context, pred, state=state)
    with pytest.raises(IntentError, match="MEASURED"):
        context[0].accept_outcome(
            context[1], pred["payload"]["experiment_id"], obs.observation_id, token
        )


def test_boolean_or_forged_review_rejected(context):
    enable(context)
    pred = prediction(context)
    obs, token = measured(context, pred)
    c, m, _, _ = context
    with pytest.raises(IntentError, match="signed"):
        c.accept_outcome(m, pred["payload"]["experiment_id"], obs.observation_id, True)
    token["review"]["purpose"] = "holdout"
    with pytest.raises(IntentError, match="signature"):
        c.accept_outcome(m, pred["payload"]["experiment_id"], obs.observation_id, token)


def test_prior_observation_and_cross_project_prediction_rejected(context):
    enable(context)
    pred = prediction(context)
    obs, _ = measured(context, pred)
    c, m, _, _ = context
    with pytest.raises(IntentError, match="already has scientific"):
        c.predict(m, pred["payload"]["experiment_id"], {"condition": 0.0}, "new")
    c.store._conn.execute("INSERT INTO projects (id,name,created_at) VALUES ('other','Other','now')")
    c.store._conn.commit()
    c.store.save_experiment("other-exp", "", "", "", project_id="other")
    with pytest.raises(IntentError, match="project"):
        c.predict(m, "other-exp", {"condition": 0.0}, "other")


def test_duplicate_acquisition_groups_and_experiments_rejected(context):
    enable(context)
    accepted(context, group="same-acquisition")
    pred = prediction(context, group="same-acquisition")
    obs, token = measured(context, pred)
    with pytest.raises(IntentError, match="acquisition group"):
        context[0].accept_outcome(
            context[1], pred["payload"]["experiment_id"], obs.observation_id, token
        )


def test_candidate_worker_idempotency_and_manual_gate(context):
    enable(context)
    c, m, _, _ = context
    initial = c.active(m)
    freeze(context)
    outcome = accepted(context, x=-3.0, y=0.2)
    updated = c.train(m, outcome["event_id"])
    assert c.active(m) == initial and c.candidate(m) == updated["checkpoint_sha256"]
    assert c.train(m, outcome["event_id"]) == updated
    assert (
        len([e for e in c.events(m) if e["event_type"] == "INTENT_MODEL_UPDATED"]) == 1
    )
    assert (
        c.checkpoint(m, updated["checkpoint_sha256"])["state"]["replay"][-1]["id"]
        == outcome["event_id"]
    )
    with pytest.raises(IntentError, match="previously active"):
        c.restore(m, updated["checkpoint_sha256"])
    evaluation = c.evaluate(m, updated["checkpoint_sha256"])
    assert evaluation["payload"]["scientific_validation"] is False
    if not evaluation["payload"]["eligible_for_manual_promotion"]:
        with pytest.raises(IntentError, match="fails"):
            c.promote(m, evaluation["event_id"])
    c.restore(m, initial)
    assert c.candidate(m) == initial


def test_holdout_never_enters_replay_and_permission_revocation_discards_worker(context):
    enable(context)
    freeze(context)
    c, m, _, _ = context
    holdout = next(
        e
        for e in c.events(m)
        if e["event_type"] == "INTENT_OUTCOME_VERIFIED"
        and e["payload"]["purpose"] == "holdout"
    )
    with pytest.raises(IntentError, match="Holdout"):
        c.prepare_update(m, holdout["event_id"])
    outcome = accepted(context)
    job = c.prepare_update(m, outcome["event_id"])
    before = c.candidate(m)
    process = subprocess.run(
        [sys.executable, "-m", "virtual_lab.intent.worker"],
        input=canonical(job["request"]),
        capture_output=True,
        timeout=20,
    )
    c.set_policy(
        {
            "predictions_enabled": True,
            "learning_enabled": False,
            "training_projects": ["p"],
        }
    )
    with pytest.raises(IntentError, match="withdrawn"):
        c.complete_update(job["job_id"], process.stdout)
    assert c.candidate(m) == before


def test_checkpoint_tampering_and_worker_cancellation(context):
    enable(context)
    freeze(context)
    c, m, _, root = context
    outcome = accepted(context)
    job = c.prepare_update(m, outcome["event_id"])
    c.cancel_update(job["job_id"])
    with pytest.raises(IntentError, match="cancelled"):
        c.complete_update(job["job_id"], b"{}")
    sha = c.active(m)
    path = root / "intent/checkpoints" / (sha + ".json")
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(IntentError, match="integrity"):
        c.checkpoint(m, sha)


def test_model_roundtrip_resume_and_invalid_shapes():
    a = MiniModel(3)
    assert sum(len(row) for row in a.w1) + len(a.b1) + len(a.w2) + 1 == 81
    a.fit_one([0.1, 0.2, 0.3], 0.8, "first")
    b = MiniModel.from_state(json.loads(canonical(a.state())))
    assert a.digest() == b.digest()
    a.fit_one([0.3, 0.1, 0.2], 0.2, "second")
    b.fit_one([0.3, 0.1, 0.2], 0.2, "second")
    assert a.digest() == b.digest()
    state = json.loads(canonical(a.state()))
    state["w1"][0] = [1.0]
    with pytest.raises(IntentError, match="weights"):
        MiniModel.from_state(state)


def test_promotion_rollback_restart_and_no_cross_project_models(context):
    enable(context)
    c, m, _, root = context
    # A synthetic sign function tests plumbing, never scientific accuracy.
    m = c.initialize("p", SCHEMA, {"learning_rate": 0.2, "epochs_per_update": 16})
    ctx = (c, m, context[2], root)
    initial = c.active(m)
    freeze(ctx)
    for index in range(12):
        x = -3.0 if index % 2 == 0 else 3.0
        out = accepted(ctx, x=x, y=0.15 if x < 0 else 0.85)
        c.train(m, out["event_id"])
    candidate = c.candidate(m)
    evaluation = c.evaluate(m, candidate)
    assert evaluation["payload"]["eligible_for_manual_promotion"]
    assert c.active(m) == initial
    c.promote(m, evaluation["event_id"])
    assert c.active(m) == candidate
    c.restore(m, initial)
    assert c.active(m) == initial and c.candidate(m) == initial
    c.store.close()
    c.ledger.conn.close()
    c.ledger = GenesisLedger(str(root / "genesis.db"))
    c.store = ExperimentStore(str(root / "experiments.db"))
    reopened = IntentController(c.ledger, c.store, root / "intent", lease=c.lease)
    assert reopened.policy().learning_enabled and reopened.active(m) == initial
    assert reopened.models("other") == []
    assert reopened.checkpoint(m, candidate)["state"]["steps"] == 12
    assert any(e["event_type"] == "INTENT_MODEL_PROMOTED" for e in reopened.events(m))


def test_reviewer_revocation_and_demo_key_are_rejected(context, monkeypatch):
    enable(context)
    c, m, _, _ = context
    pred = prediction(context)
    obs, token = measured(context, pred)
    public = token["public_key"]
    signer = _REGISTRY[public]
    monkeypatch.setitem(
        _REGISTRY,
        public,
        TrustedSigner(
            signer.signer_id,
            public,
            "test-only",
            TrustState.REVOKED,
            [SignerRole.HUMAN_APPROVAL],
            "now",
        ),
    )
    with pytest.raises(IntentError, match="trusted"):
        c.accept_outcome(m, pred["payload"]["experiment_id"], obs.observation_id, token)
    token["public_key"] = (
        "a4d19f5a5e6a6d57433afd760e2efb5efa44427b7e1f2d642763210196589912"
    )
    with pytest.raises(IntentError, match="non-demonstration"):
        c.accept_outcome(m, pred["payload"]["experiment_id"], obs.observation_id, token)


def test_worker_race_forged_replay_and_future_measurement_rejected(context):
    enable(context)
    freeze(context)
    c, m, _, root = context
    a = accepted(context, x=-2.0)
    b = accepted(context, x=2.0)
    job = c.prepare_update(m, a["event_id"])
    c.train(m, b["event_id"])
    worker = subprocess.run(
        [sys.executable, "-m", "virtual_lab.intent.worker"],
        input=canonical(job["request"]),
        capture_output=True,
        timeout=20,
    )
    with pytest.raises(IntentError, match="changed during training"):
        c.complete_update(job["job_id"], worker.stdout)
    job = c.prepare_update(m, a["event_id"])
    worker = subprocess.run(
        [sys.executable, "-m", "virtual_lab.intent.worker"],
        input=canonical(job["request"]),
        capture_output=True,
        timeout=20,
    )
    result = json.loads(worker.stdout)
    result["state"]["replay"][-1]["y"] = 0.123
    with pytest.raises(IntentError, match="replay"):
        c.complete_update(job["job_id"], canonical(result))
    assert any(e["event_type"] == "INTENT_UPDATE_REJECTED" for e in c.events(m))
    pred = prediction(context)
    obs, token = measured(
        context,
        pred,
        acquired=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    with pytest.raises(IntentError, match="present"):
        c.accept_outcome(m, pred["payload"]["experiment_id"], obs.observation_id, token)


def test_gui_defaults_project_isolation_and_real_async_worker(
    context, qtbot, monkeypatch
):
    from virtual_lab.gui.intent_workspace import IntentWorkspace
    from virtual_lab.gui.services.study_service import StudyService
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from PySide6.QtCore import Qt

    c, m, _, root = context
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(root))
    workspace = WorkspaceState()
    study = StudyService(workspace, c.ledger, c.store)
    study.create_experiment("p", "Planned fixture", "Software test only")
    panel = IntentWorkspace(workspace, study, lease=c.lease)
    qtbot.addWidget(panel)
    assert not panel.predictions.isChecked() and not panel.learning.isChecked()
    assert workspace.ai_state == "off" and panel.models.count() == 1
    panel.predictions.setChecked(True)
    panel.save_policy()
    panel.conditions.setText('{"condition":0}')
    panel.group.setText("prospective-fixture")
    panel.predict()
    assert "PREDICTED" in panel.status.text()
    assert (
        study.store.get_observations_for_experiment(workspace.active_experiment.id)
        == []
    )
    assert not panel.learning.isChecked() and workspace.ai_state == "off"
    enable(context)
    freeze(context)
    outcome = accepted(context)
    study.activate(outcome["payload"]["experiment_id"])
    panel.refresh()
    panel.models.setCurrentIndex(panel.models.findData(m))
    panel.refresh_model()
    for i in range(panel.outcomes.count()):
        if panel.outcomes.item(i).data(Qt.UserRole) == outcome["event_id"]:
            panel.outcomes.setCurrentRow(i)
    initial = c.active(m)
    panel.train()
    assert panel.busy
    qtbot.waitUntil(lambda: not panel.busy, timeout=15000)
    assert c.candidate(m) != initial and c.active(m) == initial
    assert "Candidate checkpoint committed" in panel.status.text()
    other = study.create_project("Other")
    study.create_experiment(other, "Other planned fixture", "Software test only")
    assert panel.models.count() == 0 and panel.conditions.text() == ""
    assert not panel.project_training.isChecked()
    panel.close()


def test_gui_cancellation_discards_result(context, qtbot, monkeypatch):
    from virtual_lab.gui.intent_workspace import IntentWorkspace
    from virtual_lab.gui.services.study_service import StudyService
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from PySide6.QtCore import Qt

    c, m, _, root = context
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(root))
    enable(context)
    freeze(context)
    outcome = accepted(context)
    workspace = WorkspaceState()
    study = StudyService(workspace, c.ledger, c.store)
    study.activate(outcome["payload"]["experiment_id"])
    panel = IntentWorkspace(workspace, study, lease=c.lease)
    qtbot.addWidget(panel)
    for i in range(panel.outcomes.count()):
        if panel.outcomes.item(i).data(Qt.UserRole) == outcome["event_id"]:
            panel.outcomes.setCurrentRow(i)
    initial = c.candidate(m)
    panel.train()
    panel.cancel()
    qtbot.waitUntil(lambda: not panel.busy, timeout=15000)
    assert c.candidate(m) == initial and not c._jobs
    assert any(e["event_type"] == "INTENT_UPDATE_CANCELLED" for e in c.events(m))


def test_central_settings_scope_cannot_be_bypassed_by_ledger_permission(context):
    enable(context)
    c, model, _, _ = context
    value = c.settings_repository.load().model_dump()
    value['project_rules'] = {'p': {'predictions': False}}
    c.settings_repository.save(value)
    with pytest.raises(PermissionError):
        prediction(context)
    assert not [e for e in c.events(model) if e['event_type']=='INTENT_PREDICTION_COMMITTED']


def test_shared_resource_slot_and_revocation_before_training_commit(context):
    from virtual_lab.settings import SettingsService
    enable(context)
    c, model_id, _, _ = context
    freeze(context)
    outcome=accepted(context)
    c.settings_service=SettingsService(c.settings_repository)
    c.settings_service.reserve('inference')
    with pytest.raises(RuntimeError,match='active'):
        c.prepare_update(model_id,outcome['event_id'])
    c.settings_service.release('inference')
    job=c.prepare_update(model_id,outcome['event_id'])
    assert c.settings_service.busy
    request=job['request']
    model=MiniModel.from_state(request['state'])
    metrics=model.fit_one(request['x'],request['y'],request['example_id'])
    value=c.settings_repository.load().model_dump()
    value['experiment_rules']={outcome['payload']['experiment_id']:{'learning':False}}
    c.settings_repository.save(value)
    active=c.active(model_id)
    with pytest.raises(PermissionError):
        c.complete_update(job['job_id'],canonical({'state':model.state(),'metrics':metrics}))
    assert not c.settings_service.busy and c.active(model_id)==active
    assert not [e for e in c.events(model_id) if e['event_type']=='INTENT_MODEL_UPDATED']


def test_checkpoint_disk_gate_prevents_new_publication(context,monkeypatch):
    import shutil
    from types import SimpleNamespace
    c, model, _, _ = context
    before=set(c.checkpoints.iterdir())
    monkeypatch.setattr(shutil,'disk_usage',lambda _:SimpleNamespace(free=0))
    with pytest.raises(IntentError,match='disk'):
        c.initialize('p',SCHEMA)
    assert set(c.checkpoints.iterdir())==before
    assert len(c.models('p'))==1
