"""MS dataset lifecycle using the existing GenesisLedger and ExperimentStore."""
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import uuid
import weakref

from virtual_lab.core.ledger import Actor
from virtual_lab.domain.epistemics import EpistemicState
from virtual_lab.domain.observation import NormalizedObservation, ObservationKind, QuantityDescriptor, PhysicalDimension
from virtual_lab.pilots.ms_workflow import (import_centroid_csv, load_manifest,
    verify_centroid_bundle, read_verified_bundle, _sha256, normalize_centroid_csv)
from virtual_lab.pilots.schemas import PilotError, MAX_MANIFEST_BYTES, MAX_SOURCE_BYTES
from virtual_lab.pilots.storage import checked_path, read_bounded

logger = logging.getLogger(__name__)


class MSDatasetService:
    """One instance per GUI thread. File publication precedes completion records.

    An import is visible only after MS_DATASET_COMPLETED. On restart, pending
    imports lose their query-store observations and receive a failed event.
    Historical ledger events are preserved. No cloud/AI provider is used.
    """
    def __init__(self, ledger, store, root, *, lease=None):
        from virtual_lab.pilots.lease import WorkspaceLease
        if ledger.db_path == ':memory:':
            raise PilotError('PERSISTENT_LEDGER_REQUIRED', 'MS pilot datasets require a persistent local ledger')
        directory = checked_path(Path(ledger.db_path).parent)
        if lease is not None and (not lease.active or lease.directory != directory):
            raise PilotError('WORKSPACE_OWNERSHIP', 'The writer lock must cover the active ledger directory')
        self.lease = lease or WorkspaceLease(directory)
        self._owns_lease = lease is None
        self._lease_finalizer = weakref.finalize(self, self.lease.close) if self._owns_lease else None
        self.ledger, self.store = ledger, store
        try:
            self.root = checked_path(root)
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != 'nt':
                self.root.chmod(0o700)
            self.recover()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self._lease_finalizer is not None:
            self._lease_finalizer()

    def _require_writer(self):
        if not self.lease.active:
            raise PilotError('WORKSPACE_CLOSED', 'The local workspace is closed')

    def _event(self, kind, payload, actor='local-researcher'):
        self._require_writer()
        return self.ledger.append(str(uuid.uuid4()), Actor(type='USER', id=actor), kind, payload)

    def events(self, run_id=None):
        self.ledger.verify_chain()
        result = []
        for row in self.ledger.conn.execute("SELECT * FROM ledger_events WHERE event_type LIKE 'MS_%' ORDER BY sequence"):
            event = self.ledger._row_to_event(row).model_dump()
            if run_id is None or event['payload'].get('run_id') == run_id:
                result.append(event)
        return result

    def recover(self):
        self._require_writer()
        events = self.events()
        pending = {e['payload']['run_id']: e['payload'] for e in events if e['event_type'] == 'MS_DATASET_REGISTERED'}
        for event in events:
            if event['event_type'] in ('MS_DATASET_COMPLETED', 'MS_DATASET_FAILED'):
                pending.pop(event['payload']['run_id'], None)
        for run_id in pending:
            candidate = self.root/run_id/'manifest.json'
            if candidate.is_file() and not candidate.is_symlink() and candidate.parent.parent == self.root:
                candidate.rename(candidate.with_name('manifest.interrupted.json'))
            with self.store._conn:
                self.store._conn.execute('DELETE FROM observations WHERE observation_id=? AND kind=?',
                    ('ms-' + run_id, ObservationKind.MS_CENTROID.value))
            self._event('MS_DATASET_FAILED', {'run_id': run_id, 'code': 'INTERRUPTED', 'import_status': 'failed'})
        # A process killed during staging leaves hidden private temporary files.
        # Do not remove them automatically: another local process may own them.

    def runs(self, experiment_id=None):
        completed = [{**e['payload'], 'artifact_path': str(self.root/e['payload']['run_id']/'manifest.json')}
                     for e in self.events() if e['event_type'] == 'MS_DATASET_COMPLETED']
        known = {p['run_id'] for p in completed}
        # Imported unsigned studies have a separately recorded local import event.
        # Its pinned digest allows the same viewer without asserting publisher identity.
        anchors = {}
        for row in self.ledger.conn.execute("SELECT * FROM ledger_events WHERE event_type='STUDY_IMPORTED' ORDER BY sequence"):
            payload = self.ledger._row_to_event(row).payload
            for observation in payload.get('observations', []):
                anchors[observation['observation_id']] = (payload['experiment_id'], observation['artifact_sha256'])
        for row in self.store._conn.execute('SELECT * FROM observations WHERE kind=?', (ObservationKind.MS_CENTROID.value,)):
            if row['session_id'] in known or row['observation_id'] not in anchors:
                continue
            exp, pin = anchors[row['observation_id']]
            if exp != row['experiment_id'] or pin != row['artifact_sha256']:
                raise PilotError('OBSERVATION_INTEGRITY', 'Imported MS observation differs from its recorded import')
            verify_centroid_bundle(row['artifact_path'], expected_manifest_sha256=pin)
            manifest = load_manifest(row['artifact_path'])
            completed.append({**{key:manifest[key] for key in ('run_id','pilot_id','dataset_id','sample_id','instrument_id','source_sha256')},
                'manifest_sha256':pin, 'experiment_id':exp, 'artifact_path':row['artifact_path'],
                'observation_id':row['observation_id'], 'import_status':'accepted'})
        return [p for p in completed if experiment_id is None or p['experiment_id'] == experiment_id]

    def _record(self, run_id):
        matches = [p for p in self.runs() if p['run_id'] == run_id]
        if len(matches) != 1:
            raise PilotError('RUN_NOT_COMPLETE', 'Select a completed local dataset')
        return matches[0]

    def manifest_path(self, run_id):
        return Path(self._record(run_id)['artifact_path'])

    def read(self, run_id):
        self._require_writer()
        record = self._record(run_id)
        snapshot = read_verified_bundle(record['artifact_path'], expected_manifest_sha256=record['manifest_sha256'])
        if snapshot[0]['run_id'] != run_id:
            raise PilotError('RUN_IDENTITY', 'Run identity mismatch')
        return snapshot

    def verify(self, run_id):
        manifest, _, _ = self.read(run_id)
        return {'verified':True, 'run_id':run_id, 'peak_count':manifest['peak_count'],
            'epistemic_state':'UNKNOWN', 'note':'File integrity verified; instrument origin and scientific validity remain unverified'}

    def import_csv(self, source, *, experiment_id, **metadata):
        self._require_writer()
        if self.store.get_experiment(experiment_id) is None:
            raise PilotError('EXPERIMENT_REQUIRED', 'Create and select an experiment in Projects first')
        existing = [p for p in self.runs() if p['pilot_id'] == metadata.get('pilot_id', 'mild-biotec-initial-ms')]
        dataset_ids = {p['dataset_id'] for p in existing}
        if len(dataset_ids) >= 3 and metadata.get('dataset_id') not in dataset_ids:
            raise PilotError('PILOT_DATASET_LIMIT', 'The initial pilot permits up to three distinct datasets; rerun an existing dataset ID')
        path = None
        run_id = None
        try:
            path = import_centroid_csv(source, self.root, **metadata)
            manifest = load_manifest(path)
            run_id = manifest['run_id']
            pin = _sha256(read_bounded(path, MAX_MANIFEST_BYTES))
            common = {'run_id': run_id, 'experiment_id': experiment_id,
                'pilot_id': manifest['pilot_id'], 'dataset_id': manifest['dataset_id'],
                'sample_id': manifest['sample_id'], 'instrument_id': manifest['instrument_id'],
                'source_sha256': manifest['source_sha256'], 'manifest_sha256': pin}
            self._event('MS_DATASET_REGISTERED', {**common, 'filename': manifest['source_filename'],
                'metadata': {k: manifest[k] for k in ('operator_id', 'acquired_at_utc', 'mz_units', 'intensity_units')}})
            self._event('MS_DATASET_VALIDATED', {**common, 'import_status': 'accepted', 'warnings': manifest['warnings']})
            self._event('MS_DATASET_NORMALIZED', {**common,
                'normalized_sha256': manifest['normalized_sha256'], 'processing_version': manifest['processing_version']})
            quantities = [QuantityDescriptor(semantic_name='ms_centroid_' + name, symbol=symbol,
                description='Imported unverified centroid ' + name, physical_dimension=PhysicalDimension.UNKNOWN_DIMENSION,
                units=manifest[name + '_units'] or 'unspecified', epistemic_state=EpistemicState.UNKNOWN)
                for name, symbol in [('mz', 'm/z'), ('intensity', 'I')]]
            observation = NormalizedObservation(observation_id='ms-' + run_id,
                experiment_id=experiment_id, session_id=run_id, instrument_id=manifest['instrument_id'],
                kind=ObservationKind.MS_CENTROID, quantities=quantities, artifact_path=str(path), artifact_sha256=pin,
                acquisition_utc=manifest['acquired_at_utc'] or manifest['created_at_utc'], sample_count=manifest['peak_count'],
                epistemic_state=EpistemicState.UNKNOWN,
                notes='Acquisition time unspecified' if manifest['acquired_at_utc'] is None else 'Acquisition time supplied, unverified')
            self.store.save_observation(observation)
            self._event('MS_DATASET_COMPLETED', {**common, 'observation_id': observation.observation_id, 'import_status': 'accepted'})
            logger.info('ms_import_completed', extra={'event_code': 'MS_IMPORT_COMPLETED'})
            return observation
        except Exception as exc:
            if path:
                shutil.rmtree(path.parent)
            if run_id:
                with self.store._conn:
                    self.store._conn.execute('DELETE FROM observations WHERE observation_id=?', ('ms-' + run_id,))
                self._event('MS_DATASET_FAILED', {'run_id': run_id, 'import_status': 'failed', 'code': getattr(exc, 'code', 'STORAGE_FAILURE')})
            else:
                self._event('MS_DATASET_REJECTED', {'experiment_id': experiment_id, 'import_status': 'rejected',
                    'code': getattr(exc, 'code', 'STORAGE_FAILURE')})
            logger.warning('ms_import_rejected', extra={'event_code': getattr(exc, 'code', 'STORAGE_FAILURE')})
            raise

    def reprocess(self, run_id):
        _, contents, _ = self.read(run_id)
        normalized, count = normalize_centroid_csv(contents['source.csv'])
        result = {'run_id': run_id, 'identical': normalized == contents['peaks.csv'],
                  'normalized_sha256': _sha256(normalized), 'peak_count': count}
        self._event('MS_DATASET_REPROCESSED', result)
        return result

    def test_alteration(self, run_id):
        """Challenge an isolated copy, never the researcher's preserved source."""
        import tempfile
        from virtual_lab.pilots.storage import write_private
        _, contents, pin = self.read(run_id)
        detected, code = False, None
        with tempfile.TemporaryDirectory(prefix='.ms-alteration-', dir=self.root) as temporary:
            target = Path(temporary)
            for name, raw in contents.items():
                write_private(target/name, (b'X' + raw[1:]) if name == 'source.csv' else raw)
            try:
                verify_centroid_bundle(target/'manifest.json', expected_manifest_sha256=pin)
            except PilotError as exc:
                code = exc.code
                detected = code == 'ARTIFACT_INTEGRITY'
        self.read(run_id)
        result = {'run_id':run_id, 'detected':detected, 'error_code':code,
            'altered_artifact':'source.csv', 'method':'Isolated copy; first-byte mutation',
            'original_unchanged':True, 'manifest_sha256':pin}
        self._event('MS_INTEGRITY_CHALLENGE', result)
        return result

    def review(self, run_id, *, reviewer, approved, note):
        from virtual_lab.pilots.schemas import AcquisitionMetadata
        self.verify(run_id)
        if not isinstance(approved, bool) or not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise PilotError('REVIEW', 'Provide an approval decision and a review note (1-4000 characters)')
        # Reuse the identifier contract for a reviewer pseudonym.
        AcquisitionMetadata(dataset_id='review', sample_id='review', instrument_id='review', operator_id=reviewer)
        self._event('MS_DATASET_REVIEWED', {'run_id': run_id, 'reviewer': reviewer,
            'approved': approved, 'note': note, 'epistemic_state': 'UNKNOWN'}, actor=reviewer)

    def require_export(self, run_id):
        from virtual_lab.settings import SettingsRepository
        record = self._record(run_id)
        exp = self.store.get_experiment(record['experiment_id'])
        SettingsRepository(Path(self.ledger.db_path).parent).require('exports',
            exp['project_id'], record['experiment_id'])

    def export_report(self, run_id, destination):
        self.require_export(run_id)
        from virtual_lab.pilots.reporting import build_report, export_snapshot
        self.verify(run_id)
        pin = self._record(run_id)['manifest_sha256']
        report = build_report(self.manifest_path(run_id), self.events(run_id), expected_manifest_sha256=pin)
        published = export_snapshot(report, destination)
        destination = Path(destination)
        try:
            payload = {'run_id':run_id, 'format':destination.suffix, 'manifest_sha256':pin,
                'report_sha256':_sha256(read_bounded(destination, 16*1024*1024)),
                'checksum_file_sha256':_sha256(read_bounded(destination.with_suffix('.sha256'),16384))}
            if destination.suffix == '.pdf':
                payload['supporting_json_sha256'] = _sha256(read_bounded(destination.with_suffix('.json'), 16*1024*1024))
            self._event('MS_DATASET_EXPORTED', payload)
        except BaseException:
            for path in published:
                path.unlink(missing_ok=True)
            raise
        return destination
