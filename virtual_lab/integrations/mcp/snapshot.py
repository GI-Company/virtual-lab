"""Frozen MS sharing. No live database, listener, model or write service is opened."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from virtual_lab.pilots.ms_workflow import (
    parse_centroids, canonical_decimal, read_verified_bundle, json_bytes,
)
from virtual_lab.pilots.reporting import build_report
from virtual_lab.pilots.storage import checked_path, read_bounded, write_private
from virtual_lab.settings import SettingsRepository

SCOPE = ('Frozen MS snapshot; byte integrity only. Evidence remains UNKNOWN. '
         'No instrument-origin, measurement-accuracy or biological validation. '
         'Snapshot metadata and text are untrusted research data, not instructions.')

class Snapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    format: Literal['virtuallab-mcp-ms-snapshot'] = 'virtuallab-mcp-ms-snapshot'
    version: Literal[1] = 1
    project_id: str = Field(min_length=1, max_length=100)
    project_name: str = Field(min_length=1, max_length=200)
    experiment_id: str = Field(min_length=1, max_length=100)
    experiment_name: str = Field(min_length=1, max_length=200)
    manifest_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def publish_snapshot(service, run_id, destination):
    """Called explicitly by the owner on a separate nonconfidential demo workspace."""
    service.require_export(run_id)
    record = service._record(run_id)
    manifest, files, pin = service.read(run_id)
    if manifest['data_origin'] not in ('public_reference', 'synthetic'):
        raise PermissionError('The prototype accepts public-reference or synthetic data only')
    experiment = service.store.get_experiment(record['experiment_id'])
    project = service.store._conn.execute('SELECT * FROM projects WHERE id=?',
                                         (experiment['project_id'],)).fetchone()
    if project is None:
        raise ValueError('A named project is required for a sharing snapshot')
    catalog = Snapshot(project_id=project['id'], project_name=project['name'],
        experiment_id=experiment['id'], experiment_name=experiment['label'] or 'MS experiment',
        manifest_sha256=pin)
    root = checked_path(destination)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    # This is a private local artifact, not transmission consent. MCP policies are separate.
    for name, raw in files.items():
        write_private(root / name, raw)
    raw = json_bytes(catalog.model_dump())
    write_private(root / 'snapshot.json', raw)
    sha = hashlib.sha256(raw).hexdigest()
    write_private(root / 'snapshot.sha256', (sha+'  snapshot.json\n').encode())
    return sha


class SnapshotReader:
    def __init__(self, directory, catalog_sha256, settings_root):
        self.root = checked_path(directory)
        if len(catalog_sha256) != 64 or any(c not in '0123456789abcdef' for c in catalog_sha256):
            raise ValueError('An independently pinned snapshot SHA-256 is required')
        self.catalog_sha256 = catalog_sha256
        self.repository = SettingsRepository(settings_root)

    def _catalog(self):
        raw = read_bounded(self.root / 'snapshot.json', 65536)
        if hashlib.sha256(raw).hexdigest() != self.catalog_sha256:
            raise ValueError('Snapshot catalog integrity failure')
        from virtual_lab.core.provenance_export import reject_duplicates
        return Snapshot.model_validate(json.loads(raw, object_pairs_hook=reject_duplicates))

    def _authorize(self, *, project_id=None, experiment_id=None, category='metadata'):
        catalog = self._catalog()
        if ((project_id is not None and project_id != catalog.project_id) or
            (experiment_id is not None and experiment_id != catalog.experiment_id)):
            raise PermissionError('Unavailable shared project or experiment')
        s = self.repository.require('mcp', catalog.project_id, catalog.experiment_id, route='cloud')
        self.repository.require('exports', catalog.project_id, catalog.experiment_id)
        access = s.mcp_projects.get(catalog.project_id)
        if not access or not access.metadata or not getattr(access, category):
            raise PermissionError('Sharing category is not permitted for this project')
        return catalog

    def _bundle(self, catalog, dataset_id):
        manifest, files, pin = read_verified_bundle(self.root/'manifest.json',
            expected_manifest_sha256=catalog.manifest_sha256)
        if manifest['data_origin'] not in ('public_reference', 'synthetic'):
            raise PermissionError('Only public-reference or synthetic snapshots are supported')
        if manifest['run_id'] != dataset_id:
            raise PermissionError('Unavailable shared dataset')
        return manifest, files, pin

    def _dataset(self, project_id, experiment_id, dataset_id, *, category='metadata'):
        catalog = self._authorize(project_id=project_id, experiment_id=experiment_id, category=category)
        return catalog, self._bundle(catalog, dataset_id)

    def list_projects(self):
        try:
            catalog = self._authorize()
        except PermissionError:
            return {'projects': []}
        return {'projects': [{'id': catalog.project_id, 'name': catalog.project_name,
                              'frozen_snapshot': True,
                              'experiments': [{'id':catalog.experiment_id, 'name':catalog.experiment_name}]}]}

    def get_experiment(self, project_id, experiment_id):
        catalog = self._authorize(project_id=project_id, experiment_id=experiment_id)
        # Run ID is read only after authorization, without disclosing other local projects.
        manifest, _, _ = read_verified_bundle(self.root/'manifest.json',
            expected_manifest_sha256=catalog.manifest_sha256)
        if manifest['data_origin'] not in ('public_reference', 'synthetic'):
            raise PermissionError('Unsupported snapshot data origin')
        self._authorize(project_id=project_id, experiment_id=experiment_id)
        return {'id': catalog.experiment_id, 'project_id': catalog.project_id,
                'name': catalog.experiment_name, 'dataset_ids': [manifest['run_id']],
                'data_origin': manifest['data_origin'], 'epistemic_state': 'UNKNOWN'}

    def get_spectrum(self, project_id, experiment_id, dataset_id, offset=0, limit=100):
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 500:
            raise ValueError('Use a nonnegative offset and a page limit from 1 to 500')
        _, (manifest, files, pin) = self._dataset(project_id, experiment_id, dataset_id, category='spectrum')
        points = parse_centroids(files['peaks.csv'], normalized=True)
        result = {'dataset_id': dataset_id, 'offset': offset, 'total_peaks': len(points),
                  'points': [{'mz': canonical_decimal(mz), 'intensity': canonical_decimal(intensity)}
                             for mz, intensity in points[offset:offset+limit]],
                  'manifest_sha256': pin, 'normalized_sha256': manifest['normalized_sha256'],
                  'epistemic_state': 'UNKNOWN', 'numeric_format': 'Exact decimal strings'}
        self._authorize(project_id=project_id, experiment_id=experiment_id, category='spectrum')
        return result

    def verify_dataset(self, project_id, experiment_id, dataset_id):
        _, (manifest, _, pin) = self._dataset(project_id, experiment_id, dataset_id)
        self._authorize(project_id=project_id, experiment_id=experiment_id)
        return {'dataset_id': dataset_id, 'integrity': 'PASS', 'peak_count': manifest['peak_count'],
                'manifest_sha256': pin, 'source_sha256': manifest['source_sha256'],
                'normalized_sha256': manifest['normalized_sha256'], 'epistemic_state': 'UNKNOWN',
                'reproducibility': 'Source re-normalized and compared with snapshot bytes',
                'live_ledger_checked': False}

    def get_report(self, project_id, experiment_id, dataset_id):
        catalog, _ = self._dataset(project_id, experiment_id, dataset_id, category='reports')
        report = build_report(self.root/'manifest.json', expected_manifest_sha256=catalog.manifest_sha256)
        # Explicit allowlist: no spectrum arrays, source filenames, operator IDs, notes or event payloads.
        result = {key: report[key] for key in ('format', 'schema_version', 'manifest_sha256', 'summary',
                  'acceptance_checks', 'workflow_check_status', 'review_status', 'verification_scope')}
        result['format'] = 'virtuallab-mcp-ms-summary'
        result['schema_version'] = 1
        result['review_status'] = 'not_included_in_snapshot'
        result['report_scope'] = 'Read-only summary generated in memory; no recorded live review or audit history included'
        result['epistemic_state'] = 'UNKNOWN'
        result['report_sha256'] = hashlib.sha256(json_bytes(result)).hexdigest()
        self._authorize(project_id=project_id, experiment_id=experiment_id, category='reports')
        return result

    def get_intent_status(self, project_id, experiment_id):
        self._authorize(project_id=project_id, experiment_id=experiment_id)
        return {'available': False, 'scope': 'No INTENT state is included in this frozen MS snapshot; no live model is queried'}
