import json
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.core.provenance_export import explain_provenance
from scripts.build_vlab_bundle import build_vlab_bundle


def test_nested_prediction_manifest_is_verified(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    ledger = GenesisLedger(str(workspace / 'genesis.db'))
    ledger.conn.close()
    prediction = workspace / 'computational' / 'run'
    prediction.mkdir(parents=True)
    (prediction / 'manifest.json').write_text(json.dumps({'epistemic_state': 'PREDICTED'}))
    bundle = tmp_path / 'experiment.vlab'
    build_vlab_bundle(str(workspace), str(bundle))
    report = explain_provenance(str(bundle))
    assert 'Error:' not in report
    assert 'Genesis hash chain: VERIFIED' in report
