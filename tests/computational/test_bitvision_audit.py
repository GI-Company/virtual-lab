import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from virtual_lab.computational.bitvision import audit_archive
from virtual_lab.computational.requests import BitVisionAuditRequest, parse_request


def _csv(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue()


def fixture(path, *, summary_return=1.0, delta_return=1.0, remove_untreated=False):
    checkpoint = dict(split='heldout', accession='P28482', regime='normal', variant='checkpoint', seed=11,
                      eradicated=True, failed=False, **{'return': 1.0}, steps=1, healthy=.8, infected=.0,
                      toxicity=.1, max_resistance=.0, mean_total_dose_per_step=.5)
    untreated = dict(checkpoint, variant='untreated', eradicated=False, failed=True, **{'return': 0.0},
                     steps=3, healthy=.2, infected=.6, toxicity=.0, mean_total_dose_per_step=.0)
    summary = []
    for record in (checkpoint, untreated):
        summary.append(dict(split='heldout', accession='P28482', regime='normal', variant=record['variant'],
                            episodes=1, eradication_rate=int(record['eradicated']), failure_rate=int(record['failed']),
                            mean_return=summary_return if record['variant']=='checkpoint' else 0,
                            median_steps=record['steps'], mean_final_healthy=record['healthy'],
                            mean_final_infected=record['infected'], mean_final_toxicity=record['toxicity'],
                            mean_max_resistance=record['max_resistance'],
                            mean_total_dose_per_step=record['mean_total_dose_per_step']))
    deltas = [dict(split='heldout', accession='P28482', regime='normal', delta_eradication_rate=1,
                   delta_failure_rate=-1, delta_return=delta_return, delta_final_healthy=.6,
                   delta_final_infected=-.6, delta_toxicity=.1)]
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('episode_results.json', json.dumps(dict(checkpoint_update=500,
            records=[checkpoint] if remove_untreated else [checkpoint, untreated])))
        archive.writestr('summary.csv', _csv(summary))
        archive.writestr('paired_deltas.csv', _csv(deltas))
        archive.writestr('action_diagnostics.json', json.dumps([dict(dose_mean=[.95])]))
        archive.writestr('checkpoint_000500.pt', b'not deserialized')
    return path


def test_audit_recomputes_pairs_and_retains_limitations(tmp_path):
    result = audit_archive(fixture(tmp_path/'evaluation.zip'))
    assert result['episode_count']==2 and result['paired_seed_count']==1
    assert result['breakdown'][0]['checkpoint_eradication_rate']==1
    assert result['status']=='SIMULATOR_ONLY'
    assert any('baseline' in note for note in result['limitations'])
    assert any('saturation' in issue for issue in result['issues'])


@pytest.mark.parametrize('change,expected',[
    ({'summary_return':2},'Summary mean_return'),
    ({'delta_return':2},'Paired delta_return'),
    ({'remove_untreated':True},'same-seed')])
def test_tampered_export_is_rejected(tmp_path,change,expected):
    with pytest.raises(ValueError,match=expected):audit_archive(fixture(tmp_path/'bad.zip',**change))


def test_request_roundtrip_and_no_model_execution(tmp_path):
    request=BitVisionAuditRequest(archive_path=str(tmp_path/'evaluation.zip'),
        fp16_path=str(tmp_path/'fp16.onnx'),fp32_path=str(tmp_path/'fp32.onnx'))
    assert parse_request(request.model_dump())==request
    assert request.instrument=='bitvision_simulator_audit'


def test_adapter_emits_calculated_audit(tmp_path,monkeypatch):
    from virtual_lab.computational import bitvision
    from virtual_lab.computational.artifacts import execute
    from virtual_lab.computational.adapters import adapter_for
    archive=fixture(tmp_path/'evaluation.zip')
    fp16=tmp_path/'fp16.onnx';fp32=tmp_path/'fp32.onnx'
    fp16.write_bytes(b'fp16 fixture');fp32.write_bytes(b'fp32 fixture')
    def signature(path):
        return {'sha256':'a'*64,'initializer_types':{10:105} if path==fp16 else {1:105}}
    monkeypatch.setattr(bitvision,'onnx_signature',signature)
    request=BitVisionAuditRequest(archive_path=str(archive),fp16_path=str(fp16),fp32_path=str(fp32))
    result=execute(request,adapter_for(request),tmp_path/'runs')
    manifest=result.read()
    assert manifest['epistemic_state']=='CALCULATED'
    assert manifest['source_epistemic_state']=='SIMULATED'
    assert manifest['summary']['status']=='SIMULATOR_ONLY'
    assert [a['file'] for a in manifest['artifacts']]==['bitvision-audit.json']


def test_study_export_import_preserves_audit(tmp_path,monkeypatch):
    from virtual_lab.computational import bitvision
    from virtual_lab.computational.artifacts import execute,register
    from virtual_lab.computational.adapters import adapter_for
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from virtual_lab.gui.services.study_service import StudyService
    def service(root):
        root.mkdir();monkeypatch.setenv('VIRTUALLAB_DATA_DIR',str(root))
        return StudyService(WorkspaceState(),GenesisLedger(str(root/'ledger.db')),
                            ExperimentStore(str(root/'experiments.db')))
    source=service(tmp_path/'source')
    exp=source.create_experiment(source.create_project('Policy evaluation'),'Simulator audit','What do the paired seeds show?')
    archive=fixture(tmp_path/'episodes.zip')
    fp16=tmp_path/'a.onnx';fp32=tmp_path/'b.onnx';fp16.write_bytes(b'a');fp32.write_bytes(b'b')
    monkeypatch.setattr(bitvision,'onnx_signature',lambda path:{'initializer_types':{10:105} if path==fp16 else {1:105}})
    request=BitVisionAuditRequest(archive_path=str(archive),fp16_path=str(fp16),fp32_path=str(fp32),experiment_id=exp)
    run=execute(request,adapter_for(request));obs=register(run,source.ledger,source.store)
    assert source.inspect(obs)['epistemic_state']=='CALCULATED'
    bundle=source.export_study(tmp_path/'policy.vlab-study')
    recipient=service(tmp_path/'recipient');recipient.import_study(bundle)
    restored=recipient.workspace.active_experiment.observations[0]
    assert recipient.inspect(restored)['summary']['status']=='SIMULATOR_ONLY'


def test_computational_gui_builds_local_request(qtbot,tmp_path,monkeypatch):
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from virtual_lab.gui.computational_workspace import ComputationalWorkspace
    monkeypatch.setenv('VIRTUALLAB_DATA_DIR',str(tmp_path))
    panel=ComputationalWorkspace(WorkspaceState(),GenesisLedger(str(tmp_path/'ledger.db')))
    qtbot.addWidget(panel)
    panel.inputs.setCurrentIndex(2)
    panel.bitvision_archive.setText(str(tmp_path/'episodes.zip'))
    panel.bitvision_fp16.setText(str(tmp_path/'a.onnx'))
    panel.bitvision_fp32.setText(str(tmp_path/'b.onnx'))
    request=panel._request()
    assert request.instrument=='bitvision_simulator_audit'
    assert request.archive_path==str(tmp_path/'episodes.zip')
    assert 'BitVision audit'==panel.inputs.tabText(2)
