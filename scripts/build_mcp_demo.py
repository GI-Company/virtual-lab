"""Prepare a NEW isolated public-reference MS snapshot; sharing remains disabled."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def build(source, output):
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.pilots.datasets import MSDatasetService
    from virtual_lab.pilots.storage import checked_path
    from virtual_lab.integrations.mcp.snapshot import publish_snapshot
    from virtual_lab.settings import SettingsRepository

    root = checked_path(output)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    engine = root / 'private-engine'
    engine.mkdir(mode=0o700)
    ledger = GenesisLedger(str(engine / 'genesis.db'))
    store = ExperimentStore(str(engine / 'experiments.db'))
    service = None
    try:
        project, experiment = str(uuid.uuid4()), str(uuid.uuid4())
        with store._conn:
            store._conn.execute('INSERT INTO projects (id,name,created_at) VALUES (?,?,?)',
                (project, 'Public-reference MS integration demo', datetime.now(timezone.utc).isoformat()))
        store.save_experiment(experiment, '', '', '', project_id=project,
                              label='Public BSA reference — workflow inspection only')
        service = MSDatasetService(ledger, store, engine / 'runs')
        observation = service.import_csv(source, experiment_id=experiment,
            dataset_id='public-ms-demo', sample_id='public-reference', instrument_id='unverified-reference',
            operator_id='local-demo', approved_nonconfidential=True, data_origin='public_reference')
        pin = publish_snapshot(service, observation.session_id, root / 'snapshot')
        # Explicit project categories are initially denied, including raw spectrum sharing.
        settings = SettingsRepository(root / 'access-policy')
        settings.save(settings.load())
        manifest, _, _ = service.read(observation.session_id)
        result = {'snapshot_sha256': pin, 'project_id': project, 'experiment_id': experiment,
                  'dataset_id': observation.session_id, 'peak_count': manifest['peak_count'],
                  'sharing': 'disabled; enable only in this isolated access-policy after reviewing categories',
                  'source_scope': 'User-confirmed public reference; UNKNOWN scientific evidence'}
        (root / 'demo.json').write_text(json.dumps(result, indent=2)+'\n')
        return result
    finally:
        if service is not None:
            service.close()
        store.close()
        ledger.conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-reference-confirmed', action='store_true', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), indent=2))


if __name__ == '__main__':
    main()
