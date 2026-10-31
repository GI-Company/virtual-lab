"""Ledger-owned experimental numerical learning with independently reviewed labels.

No MS workflow approval, caller boolean or model prediction is a training grant.
Production reviews require a separately trusted non-demonstration Ed25519 key.
"""

from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
from nacl.signing import VerifyKey
from virtual_lab.core.ledger import Actor
from virtual_lab.core.provenance_export import reject_duplicates
from virtual_lab.core.trusted_signers import get_signer, verify_signer_role, SignerRole
from virtual_lab.domain.epistemics import EpistemicState, QualityState
from virtual_lab.domain.observation import ObservationKind
from virtual_lab.pilots.storage import checked_path, read_bounded, write_private
from virtual_lab.intent.model import MiniModel, canonical
from virtual_lab.intent.schema import (
    FeaturesPolicy,
    TargetSchema,
    LearningConfig,
    MeasuredOutcome,
    Review,
    IntentError,
)

DEMO_KEYS = {
    "a4d19f5a5e6a6d57433afd760e2efb5efa44427b7e1f2d642763210196589912",
    "414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise IntentError("Timezone-aware timestamp required")
    return result


def parse(raw):
    return json.loads(
        raw,
        object_pairs_hook=reject_duplicates,
        parse_constant=lambda _: (_ for _ in ()).throw(IntentError("Nonfinite JSON")),
    )


class IntentController:
    def __init__(self, ledger, store, root, *, lease):
        self.ledger, self.store, self.lease = ledger, store, lease
        if not lease.active or lease.directory != checked_path(
            Path(ledger.db_path).parent
        ):
            raise IntentError("Active workspace writer lease required")
        self.root = checked_path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.checkpoints = checked_path(self.root / "checkpoints")
        self.checkpoints.mkdir(mode=0o700, exist_ok=True)
        self._jobs = {}

    def events(self, model_id=None):
        if not self.lease.active:
            raise IntentError("Workspace is closed")
        self.ledger.verify_chain()
        events = [
            self.ledger._row_to_event(row).model_dump()
            for row in self.ledger.conn.execute(
                "SELECT * FROM ledger_events WHERE event_type LIKE 'INTENT_%' ORDER BY sequence"
            )
        ]
        return [
            e
            for e in events
            if model_id is None or e["payload"].get("model_id") == model_id
        ]

    def _event(self, kind, payload, actor="local-researcher"):
        if not self.lease.active:
            raise IntentError("Workspace is closed")
        event_id = str(uuid.uuid4())
        self.ledger.append(event_id, Actor(type="USER", id=actor), kind, payload)
        return next(e for e in reversed(self.events()) if e["event_id"] == event_id)

    def policy(self):
        latest = next(
            (
                e
                for e in reversed(self.events())
                if e["event_type"] == "INTENT_POLICY_CHANGED"
            ),
            None,
        )
        return (
            FeaturesPolicy.model_validate(latest["payload"]["policy"])
            if latest
            else FeaturesPolicy()
        )

    def set_policy(self, policy):
        policy = FeaturesPolicy.model_validate(policy)
        for project in policy.training_projects:
            if not self.store._conn.execute(
                "SELECT 1 FROM projects WHERE id=?", (project,)
            ).fetchone():
                raise IntentError("Unknown approved training project")
        self._event("INTENT_POLICY_CHANGED", {"policy": policy.model_dump()})
        return policy

    def models(self, project_id):
        return [
            e["payload"]
            for e in self.events()
            if e["event_type"] == "INTENT_MODEL_REGISTERED"
            and e["payload"]["project_id"] == project_id
        ]

    def _model(self, model_id):
        found = [
            e["payload"]
            for e in self.events(model_id)
            if e["event_type"] == "INTENT_MODEL_REGISTERED"
        ]
        if len(found) != 1:
            raise IntentError("Select a registered local model")
        return found[0]

    def _experiment(self, model, experiment_id):
        exp = self.store.get_experiment(experiment_id)
        if not exp or exp["project_id"] != model["project_id"]:
            raise IntentError("Experiment does not belong to this model project")
        return exp

    def _publish(self, payload):
        raw = canonical(payload)
        if len(raw) > 2 * 1024 * 1024:
            raise IntentError("Checkpoint exceeds size limit")
        sha = digest(raw)
        path = self.checkpoints / (sha + ".json")
        if path.exists():
            if read_bounded(path, 2 * 1024 * 1024) != raw:
                raise IntentError("Checkpoint integrity conflict")
        else:
            write_private(path, raw)
        return sha

    def checkpoint(self, model_id, sha):
        if (
            not isinstance(sha, str)
            or len(sha) != 64
            or any(c not in "0123456789abcdef" for c in sha)
        ):
            raise IntentError("Invalid checkpoint reference")
        registered = {
            e["payload"].get("checkpoint_sha256")
            for e in self.events(model_id)
            if e["event_type"] in ("INTENT_MODEL_REGISTERED", "INTENT_MODEL_UPDATED")
        }
        if sha not in registered:
            raise IntentError("Checkpoint is not committed in Genesis")
        raw = read_bounded(self.checkpoints / (sha + ".json"), 2 * 1024 * 1024)
        if digest(raw) != sha:
            raise IntentError("Checkpoint integrity mismatch")
        data = parse(raw)
        if (
            set(data)
            != {
                "format",
                "model_id",
                "project_id",
                "schema",
                "state",
                "parent",
                "outcome_id",
            }
            or data["format"] != "intent-checkpoint-v1"
        ):
            raise IntentError("Unsupported checkpoint envelope")
        model = self._model(model_id)
        schema = TargetSchema.model_validate(data["schema"])
        state = MiniModel.from_state(data["state"])
        if (
            data["model_id"] != model_id
            or data["project_id"] != model["project_id"]
            or digest(canonical(schema.model_dump())) != model["schema_sha256"]
            or state.features != len(schema.features)
        ):
            raise IntentError("Checkpoint identity/schema mismatch")
        return data

    def initialize(self, project_id, schema, config=None):
        if not self.store._conn.execute(
            "SELECT 1 FROM projects WHERE id=?", (project_id,)
        ).fetchone():
            raise IntentError("Select an existing project")
        if not self.lease.active:
            raise IntentError("Workspace is closed")
        schema = TargetSchema.model_validate(schema)
        config = LearningConfig.model_validate(config or {})
        model_id = str(uuid.uuid4())
        model = MiniModel(len(schema.features), config)
        sha = self._publish(
            {
                "format": "intent-checkpoint-v1",
                "model_id": model_id,
                "project_id": project_id,
                "schema": schema.model_dump(),
                "state": model.state(),
                "parent": None,
                "outcome_id": None,
            }
        )
        self._event(
            "INTENT_MODEL_REGISTERED",
            {
                "model_id": model_id,
                "project_id": project_id,
                "schema_sha256": digest(canonical(schema.model_dump())),
                "checkpoint_sha256": sha,
                "schema": schema.model_dump(),
                "architecture": model.architecture,
                "status": "experimental_unvalidated",
            },
        )
        return model_id

    def active(self, model_id):
        self._model(model_id)
        return next(
            e["payload"]["checkpoint_sha256"]
            for e in reversed(self.events(model_id))
            if e["event_type"]
            in (
                "INTENT_MODEL_REGISTERED",
                "INTENT_MODEL_PROMOTED",
                "INTENT_MODEL_RESTORED",
            )
        )

    def candidate(self, model_id):
        return next(
            (
                e["payload"]["checkpoint_sha256"]
                for e in reversed(self.events(model_id))
                if e["event_type"] in ("INTENT_MODEL_UPDATED", "INTENT_MODEL_RESTORED")
            ),
            self.active(model_id),
        )

    def predict(self, model_id, experiment_id, conditions, group_id):
        if not self.policy().predictions_enabled:
            raise IntentError("INTENT predictions are disabled")
        model = self._model(model_id)
        exp = self._experiment(model, experiment_id)
        if exp["status"] != "active":
            raise IntentError("Prediction requires a planned active experiment")
        if not isinstance(group_id, str) or not 1 <= len(group_id) <= 100:
            raise IntentError("Declare an independent acquisition/study group")
        if any(
            o.kind != ObservationKind.RESEARCH_RECORD
            for o in self.store.get_observations_for_experiment(experiment_id)
        ):
            raise IntentError(
                "Experiment already has scientific observations; retrospective prediction is not prospective evidence"
            )
        if any(
            e["event_type"] == "INTENT_PREDICTION_COMMITTED"
            and e["payload"]["experiment_id"] == experiment_id
            for e in self.events(model_id)
        ):
            raise IntentError(
                "A prediction is already committed for this experiment/model"
            )
        sha = self.active(model_id)
        checkpoint = self.checkpoint(model_id, sha)
        schema = TargetSchema.model_validate(checkpoint["schema"])
        x = schema.encode(conditions)
        value = MiniModel.from_state(checkpoint["state"]).predict(x)
        return self._event(
            "INTENT_PREDICTION_COMMITTED",
            {
                "model_id": model_id,
                "project_id": model["project_id"],
                "experiment_id": experiment_id,
                "checkpoint_sha256": sha,
                "schema_sha256": model["schema_sha256"],
                "conditions": conditions,
                "features": x,
                "group_id": group_id,
                "predicted_normalized": value,
                "predicted_value": schema.target_offset + value * schema.target_scale,
                "unit": schema.outcome_unit,
                "epistemic_state": "PREDICTED",
                "uncertainty": None,
                "status": "experimental_unvalidated",
            },
        )

    def _review(self, token):
        if not isinstance(token, dict) or set(token) != {
            "review",
            "public_key",
            "signature",
        }:
            raise IntentError(
                "A signed review envelope is required; booleans are not approvals"
            )
        review = Review.model_validate(token["review"])
        key = token["public_key"]
        if (
            not isinstance(key, str)
            or len(key) != 64
            or any(c not in "0123456789abcdef" for c in key)
        ):
            raise IntentError("Invalid reviewer public key")
        if key in DEMO_KEYS or not verify_signer_role(key, SignerRole.HUMAN_APPROVAL):
            raise IntentError(
                "An independently trusted non-demonstration reviewer key is required"
            )
        signer = get_signer(key)
        if signer.signer_id != review.reviewer_id:
            raise IntentError("Reviewer identity does not match the trusted key")
        expiry = timestamp(review.expires_at_utc)
        now = datetime.now(timezone.utc)
        if expiry <= now or expiry > now + timedelta(days=30):
            raise IntentError(
                "Review is expired or exceeds the 30-day permission window"
            )
        try:
            VerifyKey(bytes.fromhex(key)).verify(
                canonical(review.model_dump()), bytes.fromhex(token["signature"])
            )
        except Exception as exc:
            raise IntentError("Review signature is invalid") from exc
        return review

    def accept_outcome(self, model_id, experiment_id, observation_id, token):
        model = self._model(model_id)
        self._experiment(model, experiment_id)
        review = self._review(token)
        predictions = [
            e
            for e in self.events(model_id)
            if e["event_type"] == "INTENT_PREDICTION_COMMITTED"
            and e["payload"]["experiment_id"] == experiment_id
        ]
        if len(predictions) != 1:
            raise IntentError("A committed pre-observation prediction is required")
        prediction = predictions[0]
        p = prediction["payload"]
        if (
            review.model_id,
            review.project_id,
            review.experiment_id,
            review.prediction_id,
            review.observation_id,
            review.schema_sha256,
            review.group_id,
        ) != (
            model_id,
            model["project_id"],
            experiment_id,
            prediction["event_id"],
            observation_id,
            model["schema_sha256"],
            p["group_id"],
        ):
            raise IntentError(
                "Signed review does not match the experiment/prediction/schema"
            )
        observations = [
            o
            for o in self.store.get_observations_for_experiment(experiment_id)
            if o.observation_id == observation_id
        ]
        if len(observations) != 1:
            raise IntentError("Select an existing experiment observation")
        obs = observations[0]
        if (
            obs.epistemic_state != EpistemicState.MEASURED
            or obs.quality_state != QualityState.VALID
        ):
            raise IntentError(
                "Genuine training requires a separately recorded MEASURED observation with VALID quality; UNKNOWN/predictions/workflow approvals are ineligible"
            )
        raw = read_bounded(obs.artifact_path, 65536)
        if (
            digest(raw) != obs.artifact_sha256
            or review.artifact_sha256 != obs.artifact_sha256
        ):
            raise IntentError("Measured observation artifact integrity mismatch")
        measured = MeasuredOutcome.model_validate(parse(raw))
        if (
            measured.experiment_id != experiment_id
            or measured.schema_sha256 != model["schema_sha256"]
            or measured.group_id != p["group_id"]
        ):
            raise IntentError("Measurement target/schema/group mismatch")
        acquired = timestamp(measured.acquired_at_utc)
        if (
            acquired != timestamp(obs.acquisition_utc)
            or acquired <= timestamp(prediction["timestamp_utc"])
            or acquired > datetime.now(timezone.utc)
        ):
            raise IntentError(
                "Measurement must be acquired after its prediction and no later than the present"
            )
        schema = TargetSchema.model_validate(model["schema"])
        y = schema.encode_target(measured.value, measured.unit)
        if any(
            e["event_type"] == "INTENT_OUTCOME_VERIFIED"
            and e["payload"]["experiment_id"] == experiment_id
            for e in self.events(model_id)
        ):
            raise IntentError("This experiment outcome was already accepted")
        if any(
            e["event_type"] == "INTENT_OUTCOME_VERIFIED"
            and e["payload"]["group_id"] == p["group_id"]
            for e in self.events(model_id)
        ):
            raise IntentError(
                "This acquisition group already contributes an outcome; scans are not independent experiments"
            )
        return self._event(
            "INTENT_OUTCOME_VERIFIED",
            {
                "model_id": model_id,
                "project_id": model["project_id"],
                "experiment_id": experiment_id,
                "prediction_id": prediction["event_id"],
                "observation_id": observation_id,
                "artifact_sha256": obs.artifact_sha256,
                "group_id": p["group_id"],
                "features": p["features"],
                "actual_normalized": y,
                "measured_value": measured.value,
                "unit": measured.unit,
                "preupdate_prediction": p["predicted_normalized"],
                "preupdate_absolute_error": abs(y - p["predicted_normalized"]),
                "purpose": review.purpose,
                "review_envelope": token,
            },
            actor=review.reviewer_id,
        )

    def _outcome(self, model_id, event_id):
        found = [
            e
            for e in self.events(model_id)
            if e["event_id"] == event_id
            and e["event_type"] == "INTENT_OUTCOME_VERIFIED"
        ]
        if len(found) != 1:
            raise IntentError("Select a verified outcome event")
        event = found[0]
        p = event["payload"]
        self._review(p["review_envelope"])
        obs = next(
            (
                o
                for o in self.store.get_observations_for_experiment(p["experiment_id"])
                if o.observation_id == p["observation_id"]
            ),
            None,
        )
        if (
            obs is None
            or obs.epistemic_state != EpistemicState.MEASURED
            or obs.quality_state != QualityState.VALID
            or digest(read_bounded(obs.artifact_path, 65536)) != p["artifact_sha256"]
        ):
            raise IntentError("Approved measurement no longer matches its evidence")
        return event

    def freeze_holdout(self, model_id, event_ids):
        if any(
            e["event_type"] in ("INTENT_MODEL_UPDATED", "INTENT_HOLDOUT_FROZEN")
            for e in self.events(model_id)
        ):
            raise IntentError("Freeze holdout once, before the first weight update")
        if (
            not isinstance(event_ids, list)
            or not 5 <= len(set(event_ids)) <= 1000
            or len(set(event_ids)) != len(event_ids)
        ):
            raise IntentError(
                "At least five distinct independent holdout outcomes are required"
            )
        outcomes = [self._outcome(model_id, i) for i in event_ids]
        if any(e["payload"]["purpose"] != "holdout" for e in outcomes):
            raise IntentError("Holdout permission required")
        if len({e["payload"]["group_id"] for e in outcomes}) != len(outcomes):
            raise IntentError("Independent holdout groups required")
        return self._event(
            "INTENT_HOLDOUT_FROZEN",
            {
                "model_id": model_id,
                "outcome_ids": event_ids,
                "snapshot_sha256": digest(canonical(outcomes)),
            },
        )

    def prepare_update(self, model_id, outcome_id):
        model = self._model(model_id)
        policy = self.policy()
        if (
            not policy.learning_enabled
            or model["project_id"] not in policy.training_projects
        ):
            raise IntentError(
                "Learning is disabled or this project is not explicitly approved for training"
            )
        for e in self.events(model_id):
            if (
                e["event_type"] == "INTENT_MODEL_UPDATED"
                and e["payload"]["outcome_id"] == outcome_id
            ):
                return {"committed": e["payload"]}
        outcome = self._outcome(model_id, outcome_id)
        p = outcome["payload"]
        if p["purpose"] != "train":
            raise IntentError("Holdout evidence may never enter replay or training")
        if not any(
            e["event_type"] == "INTENT_HOLDOUT_FROZEN" for e in self.events(model_id)
        ):
            raise IntentError("Freeze an independent holdout before training")
        parent = self.candidate(model_id)
        checkpoint = self.checkpoint(model_id, parent)
        job_id = str(uuid.uuid4())
        request = {
            "state": checkpoint["state"],
            "x": p["features"],
            "y": p["actual_normalized"],
            "example_id": outcome_id,
        }
        self._jobs[job_id] = {
            "model_id": model_id,
            "outcome_id": outcome_id,
            "parent": parent,
            "request": parse(canonical(request)),
        }
        return {"job_id": job_id, "request": request}

    def cancel_update(self, job_id):
        job = self._jobs.pop(job_id, None)
        if job:
            self._event(
                "INTENT_UPDATE_CANCELLED",
                {"model_id": job["model_id"], "outcome_id": job["outcome_id"]},
            )

    def complete_update(self, job_id, raw):
        job = self._jobs.pop(job_id, None)
        if job is None:
            raise IntentError("Unknown, cancelled or completed training job")
        try:
            return self._complete_update(job, raw)
        except Exception as exc:
            self._event(
                "INTENT_UPDATE_REJECTED",
                {
                    "model_id": job["model_id"],
                    "outcome_id": job["outcome_id"],
                    "reason": str(exc)[:500],
                },
            )
            raise

    def _complete_update(self, job, raw):
        if len(raw) > 2 * 1024 * 1024:
            raise IntentError("Worker result exceeds limit")
        model_id = job["model_id"]
        model = self._model(model_id)
        policy = self.policy()
        if (
            not policy.learning_enabled
            or model["project_id"] not in policy.training_projects
        ):
            raise IntentError(
                "Training permission was withdrawn; worker result discarded"
            )
        self._outcome(model_id, job["outcome_id"])
        for e in self.events(model_id):
            if (
                e["event_type"] == "INTENT_MODEL_UPDATED"
                and e["payload"]["outcome_id"] == job["outcome_id"]
            ):
                return e["payload"]
        if self.candidate(model_id) != job["parent"]:
            raise IntentError(
                "Candidate changed during training; retry from the new checkpoint"
            )
        result = parse(raw)
        if set(result) != {"state", "metrics"}:
            raise IntentError("Invalid worker result")
        updated = MiniModel.from_state(result["state"])
        parent = self.checkpoint(model_id, job["parent"])
        if (
            updated.features != len(model["schema"]["features"])
            or updated.config.model_dump() != parent["state"]["config"]
            or updated.steps != parent["state"]["steps"] + 1
        ):
            raise IntentError(
                "Worker changed architecture/configuration or step lineage"
            )
        expected_replay = (
            (
                parent["state"]["replay"]
                + [
                    {
                        "x": job["request"]["x"],
                        "y": job["request"]["y"],
                        "id": job["outcome_id"],
                    }
                ]
            )[-updated.config.replay_capacity :]
            if updated.config.replay_capacity
            else []
        )
        if updated.replay != expected_replay:
            raise IntentError("Worker replay does not match approved evidence history")
        expected_pre = MiniModel.from_state(parent["state"]).predict(
            job["request"]["x"]
        )
        metrics = result["metrics"]
        if (
            not isinstance(metrics, dict)
            or set(metrics) != {"preupdate_prediction", "absolute_error"}
            or metrics["preupdate_prediction"] != expected_pre
            or metrics["absolute_error"] != abs(expected_pre - job["request"]["y"])
        ):
            raise IntentError(
                "Worker metrics do not match the approved pre-update state"
            )
        sha = self._publish(
            {
                **parent,
                "state": updated.state(),
                "parent": job["parent"],
                "outcome_id": job["outcome_id"],
            }
        )
        outcome = self._outcome(model_id, job["outcome_id"])["payload"]
        return self._event(
            "INTENT_MODEL_UPDATED",
            {
                "model_id": model_id,
                "project_id": model["project_id"],
                "outcome_id": job["outcome_id"],
                "experiment_id": outcome["experiment_id"],
                "group_id": outcome["group_id"],
                "parent_checkpoint": job["parent"],
                "checkpoint_sha256": sha,
                "worker_metrics": result["metrics"],
                "status": "candidate_only",
                "steps": updated.steps,
            },
        )["payload"]

    def train(self, model_id, outcome_id):
        job = self.prepare_update(model_id, outcome_id)
        if "committed" in job:
            return job["committed"]
        try:
            process = subprocess.run(
                [sys.executable, "-m", "virtual_lab.intent.worker"],
                input=canonical(job["request"]),
                capture_output=True,
                timeout=30,
            )
            if process.returncode:
                raise IntentError(
                    "Numerical training worker failed; active checkpoint unchanged"
                )
            return self.complete_update(job["job_id"], process.stdout)
        except BaseException:
            self.cancel_update(job["job_id"])
            raise

    def evaluate(self, model_id, sha):
        candidate = MiniModel.from_state(self.checkpoint(model_id, sha)["state"])
        active = MiniModel.from_state(
            self.checkpoint(model_id, self.active(model_id))["state"]
        )
        frozen = next(
            (
                e
                for e in self.events(model_id)
                if e["event_type"] == "INTENT_HOLDOUT_FROZEN"
            ),
            None,
        )
        if frozen is None:
            raise IntentError("Independent frozen holdout required")
        outcomes = [
            self._outcome(model_id, i) for i in frozen["payload"]["outcome_ids"]
        ]
        if digest(canonical(outcomes)) != frozen["payload"]["snapshot_sha256"]:
            raise IntentError("Frozen holdout changed")
        training = [
            self._outcome(model_id, e["payload"]["outcome_id"])
            for e in self.events(model_id)
            if e["event_type"] == "INTENT_MODEL_UPDATED"
        ]
        if not training:
            raise IntentError("No committed training examples for baseline comparison")
        if {e["payload"]["group_id"] for e in outcomes} & {
            e["payload"]["group_id"] for e in training
        }:
            raise IntentError("Training/holdout acquisition leakage")
        baseline = sum(e["payload"]["actual_normalized"] for e in training) / len(
            training
        )

        def mae(predict):
            return sum(
                abs(
                    predict(e["payload"]["features"])
                    - e["payload"]["actual_normalized"]
                )
                for e in outcomes
            ) / len(outcomes)

        cm, am, bm = (
            mae(candidate.predict),
            mae(active.predict),
            mae(lambda _: baseline),
        )
        eligible = cm <= am and cm < bm
        return self._event(
            "INTENT_MODEL_EVALUATED",
            {
                "model_id": model_id,
                "checkpoint_sha256": sha,
                "active_checkpoint": self.active(model_id),
                "holdout_sha256": frozen["payload"]["snapshot_sha256"],
                "groups": len(outcomes),
                "candidate_mae": cm,
                "active_mae": am,
                "training_mean_baseline_mae": bm,
                "eligible_for_manual_promotion": eligible,
                "scientific_validation": False,
            },
        )

    def promote(self, model_id, evaluation_id):
        evaluations = [
            e
            for e in self.events(model_id)
            if e["event_id"] == evaluation_id
            and e["event_type"] == "INTENT_MODEL_EVALUATED"
        ]
        if len(evaluations) != 1:
            raise IntentError("Select a committed evaluation")
        old = evaluations[0]["payload"]
        if (
            self.active(model_id) != old["active_checkpoint"]
            or self.candidate(model_id) != old["checkpoint_sha256"]
        ):
            raise IntentError("Evaluation is stale")
        current = self.evaluate(model_id, old["checkpoint_sha256"])["payload"]
        if not current["eligible_for_manual_promotion"]:
            raise IntentError("Candidate fails independent holdout/baseline gates")
        return self._event(
            "INTENT_MODEL_PROMOTED",
            {
                "model_id": model_id,
                "checkpoint_sha256": old["checkpoint_sha256"],
                "evaluation_id": evaluation_id,
                "manual": True,
            },
        )

    def restore(self, model_id, sha):
        allowed = {
            e["payload"]["checkpoint_sha256"]
            for e in self.events(model_id)
            if e["event_type"]
            in (
                "INTENT_MODEL_REGISTERED",
                "INTENT_MODEL_PROMOTED",
                "INTENT_MODEL_RESTORED",
            )
        }
        if sha not in allowed:
            raise IntentError(
                "Only previously active checkpoints can be restored; candidates require evaluation"
            )
        self.checkpoint(model_id, sha)
        return self._event(
            "INTENT_MODEL_RESTORED",
            {
                "model_id": model_id,
                "checkpoint_sha256": sha,
                "previous_checkpoint": self.active(model_id),
            },
        )
