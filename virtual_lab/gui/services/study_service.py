"""Persistent research projects and portable, hash-checked study snapshots.

Study packages attest byte consistency, not publisher identity or scientific validity.
They are deliberately separate from the legacy signed .vlab format.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone

from virtual_lab.core.experiment import VirtualExperiment
from virtual_lab.core.ledger import Actor
from virtual_lab.computational.artifacts import CompletedRun, data_root, digest
from virtual_lab.domain.experiment_store import ExperimentStore


class StudyService:
    def __init__(self, workspace, ledger, store=None):
        self.workspace, self.ledger = workspace, ledger
        self.store = store or ExperimentStore()

    def _event(self, kind, payload):
        self.ledger.append(str(uuid.uuid4()), Actor(type="USER", id="local-researcher"), kind, payload)

    def projects(self):
        return [dict(r) for r in self.store._conn.execute("SELECT * FROM projects ORDER BY created_at, id")]

    def create_project(self, name):
        name = name.strip()
        if not name or len(name) > 200:
            raise ValueError("Enter a project name of at most 200 characters.")
        project_id = str(uuid.uuid4())
        with self.store._conn:
            self.store._conn.execute("INSERT INTO projects VALUES (?, ?, ?)",
                                     (project_id, name, datetime.now(timezone.utc).isoformat()))
        self._event("PROJECT_CREATED", {"project_id": project_id, "name": name})
        return project_id

    def create_experiment(self, project_id, label, question):
        label, question = label.strip(), question.strip()
        if not label or not question or len(label) > 200 or len(question) > 8000:
            raise ValueError("Enter an experiment name (up to 200 characters) and research question (up to 8000 characters).")
        if not any(p['id'] == project_id for p in self.projects()):
            raise ValueError("Select a project first.")
        exp = VirtualExperiment("", "", "", label=label)
        self.store.save_experiment(exp.id, "", "", "", label=label,
                                   project_id=project_id, research_question=question)
        self._event("RESEARCH_EXPERIMENT_CREATED", {"experiment_id": exp.id, "project_id": project_id,
                                                   "label": label, "research_question": question})
        self.activate(exp.id)
        return exp.id

    def activate(self, experiment_id):
        row = self.store.get_experiment(experiment_id) if experiment_id else None
        if experiment_id and row is None:
            raise ValueError("Experiment no longer exists.")
        exp = None
        if row:
            exp = VirtualExperiment(row['disease_id'], row['compound_id'], row['evidence_snapshot'],
                                    parent_id=row['parent_id'], label=row['label'])
            exp.id, exp.status = row['id'], row['status']
            exp.project_id, exp.research_question = row['project_id'], row['research_question']
            exp.observations = self.store.get_observations_for_experiment(exp.id)
        with self.store._conn:
            self.store._conn.execute("INSERT OR REPLACE INTO workspace_settings VALUES ('active_experiment', ?)",
                                     (experiment_id or "",))
        self.workspace._active_project_id = row['project_id'] if row else None
        # Clear the previous experiment's analysis before announcing the new context.
        self.workspace.current_result = None
        self.workspace.active_experiment = exp

    def update_question(self, question):
        exp = self.workspace.active_experiment
        if exp is None or not question.strip() or len(question.strip()) > 8000:
            raise ValueError("Open an experiment and enter a research question.")
        with self.store._conn:
            self.store._conn.execute('UPDATE experiments SET research_question=? WHERE id=?', (question.strip(), exp.id))
        self._event('RESEARCH_QUESTION_UPDATED', {'experiment_id': exp.id, 'research_question': question.strip()})
        self.activate(exp.id)

    def restore(self):
        row = self.store._conn.execute("SELECT value FROM workspace_settings WHERE key='active_experiment'").fetchone()
        if row and self.store.get_experiment(row[0]):
            self.activate(row[0])

    def research_records(self, experiment_id=None):
        experiment_id = experiment_id or getattr(self.workspace.active_experiment, 'id', '')
        return [(obs, self.inspect(obs)) for obs in self.store.get_observations_for_experiment(experiment_id)
                if obs.instrument_id in ('research_plan', 'research_conclusion')]

    def save_research_plan(self, hypothesis, method, expected_outcome, acceptance_criteria):
        return self._save_research_record('plan', dict(hypothesis=hypothesis, method=method,
            expected_outcome=expected_outcome, acceptance_criteria=acceptance_criteria))

    def save_research_conclusion(self, interpretation, limitations, decision, observation_ids):
        exp = self.workspace.active_experiment
        if exp is None:
            raise ValueError('Open an experiment first.')
        plans = [(obs, value) for obs, value in self.research_records(exp.id) if value['record_type'] == 'plan']
        if not plans:
            raise ValueError('Save a research plan before recording a conclusion.')
        plan, plan_value = plans[-1]
        if plan_value['research_question'] != exp.research_question:
            raise ValueError('The research question changed. Save an updated plan first.')
        observations = {obs.observation_id: obs for obs in self.store.get_observations_for_experiment(exp.id)}
        if not observation_ids or len(set(observation_ids)) != len(observation_ids):
            raise ValueError('Select one or more distinct saved results as evidence.')
        references = []
        from datetime import datetime
        before_results = True
        for observation_id in observation_ids:
            obs = observations.get(observation_id)
            if obs is None or obs.instrument_id in ('research_plan', 'research_conclusion'):
                raise ValueError('Evidence must be a saved result in this experiment.')
            self.inspect(obs)
            before_results &= datetime.fromisoformat(obs.acquisition_utc) >= datetime.fromisoformat(plan_value['created_at'])
            references.append({'observation_id': obs.observation_id, 'sha256': obs.artifact_sha256})
        return self._save_research_record('conclusion', dict(interpretation=interpretation,
            limitations=limitations, decision=decision), plan_ref={'observation_id': plan.observation_id,
            'sha256': plan.artifact_sha256}, result_refs=references,
            planning_scope='before_selected_results' if before_results else 'retrospective')

    def _save_research_record(self, record_type, content, **references):
        from virtual_lab.domain.research import ResearchRecord
        from virtual_lab.domain.observation import NormalizedObservation, ObservationKind
        from virtual_lab.domain.epistemics import EpistemicState
        exp = self.workspace.active_experiment
        if exp is None:
            raise ValueError('Open an experiment first.')
        if any(not isinstance(value, str) or not value.strip() or len(value.strip()) > 8000 for value in content.values()):
            raise ValueError('Complete each research record field using at most 8000 characters.')
        record = ResearchRecord(id=str(uuid.uuid4()), experiment_id=exp.id,
            record_type=record_type, research_question=exp.research_question,
            created_at=datetime.now(timezone.utc).isoformat(), content=content,
            epistemic_state='MODEL_ASSUMPTION' if record_type == 'plan' else 'INFERRED', **references)
        raw = record.model_dump_json().encode()
        sha = hashlib.sha256(raw).hexdigest()
        root = data_root() / 'research-records'
        root.mkdir(parents=True, exist_ok=True)
        target = root / (sha + '.json')
        # A content-addressed record is append-only. Existing bytes are checked.
        try:
            with target.open('xb') as stream:
                stream.write(raw)
        except FileExistsError:
            if target.read_bytes() != raw:
                raise ValueError('Research record artifact conflict.')
        obs = NormalizedObservation(observation_id=record.id, experiment_id=exp.id,
            session_id=record.id, instrument_id='research_' + record_type,
            kind=ObservationKind.RESEARCH_RECORD, quantities=[], artifact_path=str(target),
            artifact_sha256=sha, acquisition_utc=record.created_at,
            epistemic_state=EpistemicState(record.epistemic_state),
            notes='Human-authored research record; not a measurement or automated validation.')
        self._event('RESEARCH_' + record_type.upper() + '_SAVED', {'experiment_id': exp.id,
            'record_id': record.id, 'artifact_sha256': sha, 'artifact_path': str(target)})
        self.store.save_observation(obs)
        exp.attach_observation(obs)
        self.workspace.observationCommitted.emit(obs)
        return obs

    @staticmethod
    def _verify_research_links(observations):
        """Cross-check citations before export/import changes durable state."""
        lookup = {o.observation_id: o for o in observations}
        for obs in observations:
            if obs.instrument_id != 'research_conclusion':
                continue
            from virtual_lab.domain.research import ResearchRecord
            record = ResearchRecord.model_validate(StudyService.inspect(obs))
            for reference in [record.plan_ref, *record.result_refs]:
                linked = lookup.get(reference.observation_id)
                if linked is None or linked.experiment_id != obs.experiment_id or linked.artifact_sha256 != reference.sha256:
                    raise ValueError('Research record has a missing or mismatched evidence reference.')
            plan = lookup[record.plan_ref.observation_id]
            if plan.instrument_id != 'research_plan':
                raise ValueError('Conclusion references an invalid research plan.')
            plan_value = StudyService.inspect(plan)
            if plan_value['research_question'] != record.research_question:
                raise ValueError('Conclusion and plan research questions disagree.')
            if any(lookup[r.observation_id].instrument_id in ('research_plan', 'research_conclusion') for r in record.result_refs):
                raise ValueError('A research conclusion cannot substitute notes for result evidence.')
            scope = 'before_selected_results' if all(datetime.fromisoformat(lookup[r.observation_id].acquisition_utc)
                >= datetime.fromisoformat(plan_value['created_at']) for r in record.result_refs) else 'retrospective'
            if scope != record.planning_scope:
                raise ValueError('Research plan timing metadata disagrees with selected results.')

    def save_predictor(self, manifest_path, inputs):
        from virtual_lab.extensions.models import predict_linear
        return self._save_extension(predict_linear(manifest_path, inputs))

    def save_csv_instrument(self, manifest_path, csv_path):
        from virtual_lab.extensions.instruments import CSVInstrument
        return self._save_extension(CSVInstrument(manifest_path).acquire(csv_path))

    def _save_extension(self, result):
        from virtual_lab.extensions.records import validate_result, INSTRUMENTS
        from virtual_lab.core.canonical import canonical_json
        from virtual_lab.domain.observation import NormalizedObservation, ObservationKind
        from virtual_lab.domain.epistemics import EpistemicState
        exp = self.workspace.active_experiment
        if exp is None:
            raise ValueError('Open an experiment before attaching an extension result.')
        validate_result(result)
        record = {'format': 'vlab-notebook-extension-v1', 'run_id': str(uuid.uuid4()),
            'recorded_at': datetime.now(timezone.utc).isoformat(), 'experiment_id': exp.id,
            'result': result}
        raw = canonical_json(record); sha = hashlib.sha256(raw).hexdigest()
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('Extension record exceeds size limit.')
        root = data_root() / 'notebook-extensions'; root.mkdir(parents=True, exist_ok=True)
        target = root / (sha + '.json')
        with target.open('xb') as stream:
            import os
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        obs = NormalizedObservation(observation_id=record['run_id'], experiment_id=exp.id,
            session_id=record['run_id'], instrument_id=INSTRUMENTS[result['kind']],
            kind=ObservationKind.MODEL_EVALUATION if result['kind'] == 'predictive_model' else ObservationKind.SENSOR_STREAM, quantities=[],
            artifact_path=str(target), artifact_sha256=sha, acquisition_utc=record['recorded_at'],
            sample_count=len(result['samples']) if result['kind'] == 'instrument_import' else 1,
            epistemic_state=EpistemicState(result['epistemic_state']),
            notes='Retained source and adapter output; not independent scientific or instrument validation.')
        self._event('EXTENSION_ARTIFACT_RECORDED', {'observation_id': obs.observation_id,
            'experiment_id': exp.id, 'kind': result['kind'], 'epistemic_state': result['epistemic_state'],
            'artifact_path': str(target), 'artifact_sha256': sha})
        self.store.save_observation(obs)
        exp.attach_observation(obs)
        self.workspace.observationCommitted.emit(obs)
        return obs

    def save_calibration(self, result):
        from virtual_lab.domain.observation import NormalizedObservation, ObservationKind, QuantityDescriptor, PhysicalDimension
        from virtual_lab.domain.epistemics import EpistemicState
        exp = self.workspace.active_experiment
        if not result or exp is None or result.get('experiment_id') != exp.id:
            raise ValueError('Fit measurements in the active experiment before saving.')
        if result.get('format') != 'virtuallab-decay-calibration' or result.get('epistemic_state') != 'INFERRED':
            raise ValueError('Unsupported calibration result.')
        if self.store._conn.execute('SELECT 1 FROM observations WHERE observation_id=?', (result['id'],)).fetchone():
            raise ValueError('This calibration is already saved.')
        payload = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        sha = hashlib.sha256(payload).hexdigest()
        root = data_root() / 'calibrations'
        root.mkdir(parents=True, exist_ok=True)
        target = root / (sha + '.json')
        with tempfile.NamedTemporaryFile(dir=root, suffix='.partial', delete=False) as f:
            f.write(payload)
            temporary = Path(f.name)
        try:
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        obs = NormalizedObservation(observation_id=result['id'], experiment_id=exp.id,
            session_id=result['id'], instrument_id='decay_calibration', kind=ObservationKind.CALIBRATION,
            quantities=[QuantityDescriptor(semantic_name='mrna_decay_relative_abundance_' + hashlib.sha256(
                json.dumps(result['dataset'], sort_keys=True, allow_nan=False).encode()).hexdigest(),
                symbol='m', description=result['dataset']['title'],
                physical_dimension=PhysicalDimension.DIMENSIONLESS, units='normalized units',
                epistemic_state=EpistemicState.DERIVED)],
            artifact_path=str(target), artifact_sha256=sha, acquisition_utc=result['created_at'],
            sample_count=len(result['measurements']), epistemic_state=EpistemicState.INFERRED,
            notes=result['validation_scope'])
        self._event('CALIBRATION_SAVED', {'run_id': result['id'], 'experiment_id': exp.id,
                                        'artifact_sha256': sha, 'artifact_path': str(target)})
        self.store.save_observation(obs)
        exp.attach_observation(obs)
        self.workspace.observationCommitted.emit(obs)
        return obs

    def save_maturation_evaluation(self, payload):
        from virtual_lab.validation.maturation import validate_report
        from virtual_lab.domain.observation import NormalizedObservation, ObservationKind, QuantityDescriptor, PhysicalDimension
        from virtual_lab.domain.epistemics import EpistemicState
        result = validate_report(payload)
        exp = self.workspace.active_experiment
        if exp is None or result['experiment_id'] != exp.id:
            raise ValueError('Evaluation belongs to a different active experiment.')
        if self.store._conn.execute('SELECT 1 FROM observations WHERE observation_id=?',(result['id'],)).fetchone():
            raise ValueError('This evaluation is already saved.')
        raw = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        sha = hashlib.sha256(raw).hexdigest()
        root = data_root() / 'model-evaluations'; root.mkdir(parents=True, exist_ok=True)
        target = root / (sha + '.json')
        with tempfile.NamedTemporaryFile(dir=root, suffix='.partial', delete=False) as f:
            f.write(raw); temporary = Path(f.name)
        try:
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        obs = NormalizedObservation(observation_id=result['id'], experiment_id=exp.id,
            session_id=result['id'], instrument_id='maturation_validation', kind=ObservationKind.MODEL_EVALUATION,
            quantities=[QuantityDescriptor(semantic_name='maturation_evaluation_'+result['id'],symbol='error',
                description='Frozen-model evaluation and metadata eligibility; no biological pass/fail',
                physical_dimension=PhysicalDimension.DIMENSIONLESS,units='normalized units',
                epistemic_state=EpistemicState.CALCULATED)],
            artifact_path=str(target),artifact_sha256=sha,acquisition_utc=result['created_at'],
            sample_count=len(result['assessment']['rows']),epistemic_state=EpistemicState.CALCULATED,
            notes=result['assessment']['status'])
        self._event('MODEL_EVALUATION_SAVED',{'result_id':result['id'],'experiment_id':exp.id,
            'artifact_sha256':sha,'eligibility_status':result['assessment']['status']})
        self.store.save_observation(obs);exp.attach_observation(obs);self.workspace.observationCommitted.emit(obs)
        return obs

    def save_biological_run(self, payload):
        from virtual_lab.biology.simulation import BiologicalRun
        from virtual_lab.domain.observation import NormalizedObservation, ObservationKind, QuantityDescriptor, PhysicalDimension
        from virtual_lab.domain.epistemics import EpistemicState
        result = BiologicalRun.model_validate(payload)
        exp = self.workspace.active_experiment
        if exp is None or result.experiment_id != exp.id:
            raise ValueError('Biological run belongs to a different active experiment.')
        if self.store._conn.execute('SELECT 1 FROM observations WHERE observation_id=?', (result.id,)).fetchone():
            raise ValueError('This biological run is already saved.')
        parent = result.initial_system.last_result_id
        if parent:
            matching = next((o for o in self.store.get_observations_for_experiment(exp.id)
                             if o.observation_id == parent and o.instrument_id == 'biological_system'), None)
            if matching is None or BiologicalRun.model_validate(self.inspect(matching)).final_system != result.initial_system:
                raise ValueError('Save the exact parent state in this experiment before continuing.')
        raw = result.model_dump_json().encode()
        sha = hashlib.sha256(raw).hexdigest()
        root = data_root() / 'biological-runs'; root.mkdir(parents=True, exist_ok=True)
        target = root / (sha + '.json')
        with tempfile.NamedTemporaryFile(dir=root, suffix='.partial', delete=False) as f:
            f.write(raw); temporary = Path(f.name)
        try:
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        quantities = [QuantityDescriptor(semantic_name='biological_'+o.id,
            symbol=o.kind, description=o.identity.label+' in '+result.final_system.context,
            physical_dimension=PhysicalDimension.DIMENSIONLESS, units='normalized units',
            epistemic_state=EpistemicState.SIMULATED)
            for o in result.final_system.objects if o.kind != 'gene']
        obs = NormalizedObservation(observation_id=result.id, experiment_id=exp.id,
            session_id=result.id, instrument_id='biological_system', kind=ObservationKind.BIOLOGICAL_SYSTEM,
            quantities=quantities, artifact_path=str(target), artifact_sha256=sha,
            acquisition_utc=result.created_at, sample_count=len(result.time_h),
            epistemic_state=EpistemicState.SIMULATED,
            notes='Object identities, mechanism, and intervention history preserved. Unvalidated biological model.')
        self._event('BIOLOGICAL_RUN_SAVED', {'run_id':result.id, 'system_id':result.final_system.id,
            'revision':result.final_system.revision, 'parent_result_id':parent,
            'experiment_id':exp.id, 'artifact_sha256':sha, 'artifact_path':str(target)})
        self.store.save_observation(obs);exp.attach_observation(obs)
        self.workspace.observationCommitted.emit(obs)
        return obs

    def attach_staged(self, observation_id):
        exp = self.workspace.active_experiment
        if exp is None:
            raise ValueError("Open an experiment first.")
        obs = self.store.assign_staged_to_experiment(observation_id, exp.id)
        if obs is None:
            raise ValueError("This result is no longer in staging.")
        self._event("STAGED_OBSERVATION_ASSIGNED", {"observation_id": obs.observation_id,
                    "experiment_id": exp.id, "artifact_sha256": obs.artifact_sha256})
        exp.attach_observation(obs)
        self.workspace.observationCommitted.emit(obs)

    @staticmethod
    def inspect(obs):
        path = Path(obs.artifact_path)
        if not obs.artifact_path or not obs.artifact_sha256:
            raise ValueError("This legacy result has no verifiable artifact reference.")
        if path.is_symlink() or digest(path) != obs.artifact_sha256:
            raise ValueError("Result artifact hash mismatch.")
        if obs.instrument_id in ('extension_predictor', 'extension_csv'):
            from virtual_lab.core.canonical import strict_json_loads
            from virtual_lab.extensions.records import validate_record, INSTRUMENTS
            if path.stat().st_size > 8 * 1024 * 1024:
                raise ValueError('Extension record exceeds size limit.')
            record = validate_record(strict_json_loads(path.read_bytes()))
            result = record['result']
            expected_samples = len(result['samples']) if result['kind'] == 'instrument_import' else 1
            if (record['run_id'] != obs.observation_id or record['run_id'] != obs.session_id
                or record['experiment_id'] != obs.experiment_id or record['recorded_at'] != obs.acquisition_utc
                or result['epistemic_state'] != obs.epistemic_state.value
                or INSTRUMENTS[result['kind']] != obs.instrument_id
                or obs.kind.value != ('MODEL_EVALUATION' if result['kind'] == 'predictive_model' else 'SENSOR_STREAM')
                or obs.sample_count != expected_samples or obs.quantities):
                raise ValueError('Extension observation identity or status mismatch.')
            return record
        if obs.instrument_id in ('alphagenome', 'alphafold_db', 'bitvision_simulator_audit'):
            result = CompletedRun(str(path), obs.artifact_sha256).read()
            if result['run_id'] != obs.session_id or result['epistemic_state'] != obs.epistemic_state.value:
                raise ValueError("Result identity mismatch.")
            return result
        if obs.kind.value == 'RESEARCH_RECORD' and obs.instrument_id not in ('research_plan', 'research_conclusion'):
            raise ValueError('Unsupported research record identity.')
        if (obs.kind.value in ('SENSOR_STREAM', 'CAMERA_FRAME', 'MICROSCOPY', 'SPECTROSCOPY', 'ELECTROCHEMISTRY')
                and obs.instrument_id not in ('simulation', 'biological_system', 'decay_calibration',
                    'maturation_validation', 'research_plan', 'research_conclusion')):
            return {'format': 'raw-artifact-reference', 'artifact_file': path.name,
                'artifact_sha256': obs.artifact_sha256, 'observation_id': obs.observation_id,
                'experiment_id': obs.experiment_id, 'instrument_id': obs.instrument_id,
                'epistemic_state': obs.epistemic_state.value, 'sample_count': obs.sample_count,
                'quantities': [{'name': q.semantic_name, 'units': q.units,
                    'epistemic_state': q.epistemic_state.value} for q in obs.quantities],
                'verification_scope': 'Artifact bytes verified; raw measurements are not automatically analyzed or validated.'}
        result = json.loads(path.read_text())
        if obs.instrument_id in ('research_plan', 'research_conclusion'):
            from virtual_lab.domain.research import ResearchRecord
            parsed = ResearchRecord.model_validate(result)
            if (parsed.id != obs.observation_id or parsed.id != obs.session_id
                    or parsed.experiment_id != obs.experiment_id
                    or parsed.epistemic_state != obs.epistemic_state.value
                    or parsed.created_at != obs.acquisition_utc
                    or obs.kind.value != 'RESEARCH_RECORD'
                    or obs.instrument_id != 'research_' + parsed.record_type):
                raise ValueError('Research record identity mismatch.')
        if obs.instrument_id == 'maturation_validation':
            from virtual_lab.validation.maturation import validate_report
            validate_report(result)
            if (result['id'] != obs.observation_id or result['id'] != obs.session_id
                    or result['experiment_id'] != obs.experiment_id or obs.epistemic_state.value != 'CALCULATED'):
                raise ValueError('Evaluation identity mismatch.')
        if obs.instrument_id == 'biological_system':
            from virtual_lab.biology.simulation import BiologicalRun
            parsed = BiologicalRun.model_validate(result)
            if (parsed.id != obs.session_id or parsed.id != obs.observation_id
                    or parsed.experiment_id != obs.experiment_id or obs.epistemic_state.value != 'SIMULATED'):
                raise ValueError('Biological run identity mismatch.')
        if obs.instrument_id == 'decay_calibration':
            if (result.get('format') != 'virtuallab-decay-calibration' or result.get('schema_version') != 1
                    or result.get('id') != obs.session_id or result.get('experiment_id') != obs.experiment_id
                    or result.get('epistemic_state') != obs.epistemic_state.value):
                raise ValueError('Calibration identity mismatch.')
        if obs.instrument_id == 'simulation':
            if result['id'] != obs.session_id:
                raise ValueError("Simulation identity mismatch.")
            if result.get('schema_version') == 2:
                from virtual_lab.gui.services.research_outputs import simulation_arrays
                simulation_arrays(result)
                if (obs.epistemic_state.value != 'SIMULATED' or obs.kind.value != 'SIMULATION'
                        or result.get('experiment_id', '') not in ('', obs.experiment_id)
                        or result['created_at'] != obs.acquisition_utc):
                    raise ValueError('Simulation metadata disagrees with its saved artifact.')
        return result

    def export_result_csv(self, observation_id, destination):
        from virtual_lab.gui.services.research_outputs import simulation_csv, publish_new_file
        exp = self.workspace.active_experiment
        if exp is None:
            raise ValueError('Open an experiment first.')
        obs = next((o for o in self.store.get_observations_for_experiment(exp.id)
                    if o.observation_id == observation_id), None)
        if obs is None or obs.instrument_id not in ('simulation', 'extension_predictor', 'extension_csv'):
            raise ValueError('Select a saved simulation, predictor or CSV instrument result to export data.')
        destination = Path(destination).expanduser()
        if destination.suffix != '.csv':
            raise ValueError('Use a filename ending in .csv.')
        result = self.inspect(obs)
        if obs.instrument_id in ('extension_predictor', 'extension_csv'):
            from virtual_lab.extensions.records import result_csv
            return publish_new_file(destination, result_csv(result, obs.observation_id, obs.artifact_sha256))
        return publish_new_file(destination, simulation_csv(dict(result, experiment_id=obs.experiment_id)))

    def export_study(self, destination):
        exp = self.workspace.active_experiment
        if exp is None:
            raise ValueError("Open an experiment first.")
        row = self.store.get_experiment(exp.id)
        project = next((p for p in self.projects() if p['id'] == row['project_id']), None)
        if project is None:
            raise ValueError("This experiment needs a project before it can be shared.")
        rows = [dict(r) for r in self.store._conn.execute(
            "SELECT * FROM observations WHERE experiment_id=? ORDER BY acquisition_utc", (exp.id,))]
        self._verify_research_links(self.store.get_observations_for_experiment(exp.id))
        files = {}
        for i, obs in enumerate(self.store.get_observations_for_experiment(exp.id)):
            result = self.inspect(obs)
            original = Path(obs.artifact_path)
            names = [original.name]
            if obs.instrument_id in ('alphagenome', 'alphafold_db', 'bitvision_simulator_audit'):
                names += [a['file'] for a in result['artifacts']]
            for name in names:
                files[f"artifacts/{i}/{name}"] = (original.parent / name).read_bytes()
            rows[i]['artifact_path'] = f"artifacts/{i}/{original.name}"
        snapshot = {'format': 'virtuallab-study', 'version': 1, 'project': project,
                    'experiment': row, 'observations': rows,
                    'verification_scope': 'Byte integrity only; not publisher identity or scientific validity.',
                    'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
        if len(files) + 1 > 1000 or sum(len(raw) for raw in files.values()) > 99 * 1024 * 1024:
            raise ValueError('Study exceeds the portable package size limit.')
        destination = Path(destination)
        if destination.exists():
            raise ValueError("Choose a new filename; existing packages are preserved.")
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.partial', delete=False) as tmp:
            temporary = Path(tmp.name)
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr('study.json', json.dumps(snapshot, sort_keys=True, allow_nan=False))
                for name, raw in files.items():
                    bundle.writestr(name, raw)
            try:
                import os
                os.link(temporary, destination)
            except FileExistsError:
                raise ValueError("Choose a new filename; existing packages are preserved.") from None
        finally:
            temporary.unlink(missing_ok=True)
        self._event('STUDY_EXPORTED', {'experiment_id': exp.id, 'sha256': digest(destination)})
        return destination

    def import_study(self, source):
        # Verify all bytes and relational metadata before changing durable state.
        with zipfile.ZipFile(source) as bundle:
            entries = bundle.infolist()
            if len(entries) > 1000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
                raise ValueError("Study package exceeds size limits.")
            names = [e.filename for e in entries]
            if len(set(names)) != len(names):
                raise ValueError("Duplicate package entries.")
            for name in names:
                p = PurePosixPath(name)
                if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or str(p) != name:
                    raise ValueError("Unsafe package path.")
            from virtual_lab.core.provenance_export import reject_duplicates
            snapshot = json.loads(bundle.read('study.json'), object_pairs_hook=reject_duplicates)
            if snapshot.get('format') != 'virtuallab-study' or snapshot.get('version') != 1:
                raise ValueError("Unsupported study package.")
            if set(names) != {'study.json', *snapshot['files']}:
                raise ValueError("Package file inventory mismatch.")
            files = {name: bundle.read(name) for name in snapshot['files']}
            for name, raw in files.items():
                if hashlib.sha256(raw).hexdigest() != snapshot['files'][name]:
                    raise ValueError("Package artifact hash mismatch.")
        exp, project, rows = snapshot['experiment'], snapshot['project'], snapshot['observations']
        if exp['project_id'] != project['id'] or self.store.get_experiment(exp['id']):
            raise ValueError("Experiment already exists or project reference is invalid. Import into a separate workspace.")
        existing_project = next((p for p in self.projects() if p['id'] == project['id']), None)
        if existing_project and existing_project != project:
            raise ValueError("Project identity conflicts with the local project.")
        seen = set()
        for row in rows:
            if row['experiment_id'] != exp['id'] or row['observation_id'] in seen:
                raise ValueError("Invalid observation relationship.")
            seen.add(row['observation_id'])
            if self.store._conn.execute('SELECT 1 FROM observations WHERE observation_id=? UNION SELECT 1 FROM staging WHERE observation_id=?',
                                        (row['observation_id'], row['observation_id'])).fetchone():
                raise ValueError("A result in this package already exists locally.")
            if row['artifact_path'] not in files or snapshot['files'][row['artifact_path']] != row['artifact_sha256']:
                raise ValueError("Invalid observation artifact reference.")
        root = data_root() / 'imported-studies'
        root.mkdir(parents=True, exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix='study-', dir=root))
        try:
            for name, raw in files.items():
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            biological = {}
            for row in rows:
                row['artifact_path'] = str(target / row['artifact_path'])
                result = self.inspect(self.store._row_to_obs(row))
                if row['instrument_id'] == 'biological_system':
                    from virtual_lab.biology.simulation import BiologicalRun
                    biological[result['id']] = BiologicalRun.model_validate(result).model_dump(mode='json')
            self._verify_research_links([self.store._row_to_obs(row) for row in rows])
            for result in biological.values():
                parent = result['initial_system']['last_result_id']
                if parent and (parent not in biological or biological[parent]['final_system'] != result['initial_system']):
                    raise ValueError('Biological package is missing its exact parent state.')
            with self.store._conn:
                if not existing_project:
                    self.store._conn.execute('INSERT INTO projects (id,name,created_at) VALUES (?,?,?)',
                                             tuple(project[k] for k in ('id','name','created_at')))
                for table, records in (('experiments', [exp]), ('observations', rows)):
                    columns = [r[1] for r in self.store._conn.execute(f'PRAGMA table_info({table})')]
                    for record in records:
                        self.store._conn.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                                 tuple(record[c] for c in columns))
        except BaseException:
            shutil.rmtree(target)
            raise
        self._event('STUDY_IMPORTED', {'experiment_id': exp['id'], 'sha256': digest(Path(source)),
                                      'verification_scope': 'Byte integrity only; imported from an unsigned study package.',
                                      'observations': [{'observation_id': r['observation_id'],
                                                        'artifact_sha256': r['artifact_sha256']} for r in rows]})
        self.activate(exp['id'])
        return exp['id']
