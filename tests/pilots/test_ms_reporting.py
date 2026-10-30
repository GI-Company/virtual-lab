from pathlib import Path
import json
from virtual_lab.pilots.ms_workflow import import_centroid_csv
from virtual_lab.pilots.reporting import build_report, export_report, spectrum_summary
import pytest


def test_metrics_are_exact_and_not_ion_current():
    summary = spectrum_summary(b'mz,intensity\n100,0.1\n100,0.2\n101,0.3\n')
    assert summary['total_intensity'] == '0.6'
    assert summary['duplicate_mz_count'] == 1
    assert 'not instrument-reported' in summary['note']


def test_json_pdf_determinism_and_source_linkage(tmp_path):
    pytest.importorskip('reportlab')
    raw = tmp_path/'synthetic.csv'
    raw.write_text('mz,intensity\n100,1\n101,3\n')
    manifest = import_centroid_csv(raw, tmp_path/'runs', sample_id='synthetic',
        instrument_id='unspecified', operator_id='tester', dataset_id='synthetic-001', approved_nonconfidential=True)
    report = build_report(manifest)
    first = export_report(report, tmp_path/'one.pdf')
    second = export_report(report, tmp_path/'two.pdf')
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().startswith(b'%PDF-')
    a = export_report(report, tmp_path/'one-json.json')
    b = export_report(build_report(manifest), tmp_path/'two-json.json')
    assert a.read_bytes() == b.read_bytes()
    assert report['review_status'] == 'not_reviewed'
    assert report['reprocessing']['status'] == 'not_run'


def test_review_reprocessing_and_export_in_report(service, tmp_path):
    source = tmp_path/'synthetic.csv'
    source.write_text('mz,intensity\n101,2\n100,1\n101,3\n')
    obs = service.import_csv(source, experiment_id='exp', dataset_id='synthetic-001', sample_id='sample',
        instrument_id='instrument', operator_id='operator', approved_nonconfidential=True)
    service.reprocess(obs.session_id)
    service.review(obs.session_id, reviewer='lab-reviewer', approved=True, note='Synthetic workflow review')
    report = build_report(obs.artifact_path, service.events(obs.session_id))
    assert report['review_status'] == 'approved'
    assert report['manifest']['epistemic_state'] == 'UNKNOWN'
    assert report['summary']['total_intensity'] == '6'
    assert report['summary']['duplicate_mz_count'] == 1
    output = service.export_report(obs.session_id, tmp_path/'report.json')
    assert json.loads(output.read_bytes()) == report
    assert service.events(obs.session_id)[-1]['event_type'] == 'MS_DATASET_EXPORTED'
    with pytest.raises(ValueError, match='existing'):
        service.export_report(obs.session_id, output)


def test_acceptance_checks_do_not_invent_missing_evidence(tmp_path):
    source=tmp_path/'source.csv'
    source.write_text('mz,intensity\n100,1\n')
    path=import_centroid_csv(source,tmp_path/'runs',sample_id='s',instrument_id='i',operator_id='o',approved_nonconfidential=True)
    report=build_report(path)
    checks={c['id']:c['status'] for c in report['acceptance_checks']}
    assert checks=={'import_validity':'PASS','reproducibility':'NOT RUN','source_integrity':'PASS','traceability':'NOT RUN','intentional_alteration':'NOT RUN'}
    assert report['workflow_check_status']=='INCOMPLETE'
    assert report['manifest']['data_origin']=='unspecified'


def test_alteration_challenge_preserves_original_and_pdf_has_exact_json(service,tmp_path):
    source=tmp_path/'synthetic.csv'
    source.write_bytes(b'mz,intensity\r\n100,1\r\n101,2\r\n')
    original=source.read_bytes()
    obs=service.import_csv(source,experiment_id='exp',data_origin='synthetic',sample_id='s',instrument_id='i',operator_id='o',approved_nonconfidential=True)
    service.reprocess(obs.session_id)
    assert service.test_alteration(obs.session_id)['detected']
    assert source.read_bytes()==original
    assert (Path(obs.artifact_path).parent/'source.csv').read_bytes()==original
    report=build_report(obs.artifact_path,service.events(obs.session_id))
    assert report['workflow_check_status']=='PASS'
    assert all(check['status']=='PASS' for check in report['acceptance_checks'])
    output=service.export_report(obs.session_id,tmp_path/'report.pdf')
    companion=json.loads(output.with_suffix('.json').read_bytes())
    assert companion==report
    assert companion['manifest']['epistemic_state']=='UNKNOWN'


def test_audit_failure_rolls_back_both_report_files(service,tmp_path,monkeypatch):
    source=tmp_path/'synthetic.csv';source.write_text('mz,intensity\n100,1\n')
    obs=service.import_csv(source,experiment_id='exp',sample_id='s',instrument_id='i',operator_id='o',approved_nonconfidential=True)
    monkeypatch.setattr(service,'_event',lambda *a,**k: (_ for _ in ()).throw(OSError('audit unavailable')))
    with pytest.raises(OSError,match='audit unavailable'):
        service.export_report(obs.session_id,tmp_path/'report.pdf')
    assert not (tmp_path/'report.pdf').exists() and not (tmp_path/'report.json').exists()


def test_report_limits_fail_before_publishing(service,tmp_path,monkeypatch):
    from virtual_lab.pilots import reporting
    source=tmp_path/'synthetic.csv';source.write_text('mz,intensity\n100,1\n')
    obs=service.import_csv(source,experiment_id='exp',sample_id='s',instrument_id='i',operator_id='o',approved_nonconfidential=True)
    monkeypatch.setattr(reporting,'MAX_REPORT_BYTES',100)
    with pytest.raises(ValueError,match='16 MiB'):
        service.export_report(obs.session_id,tmp_path/'report.pdf')
    assert not (tmp_path/'report.pdf').exists() and not (tmp_path/'report.json').exists()


def test_normalized_display_uses_normalized_size_limit(monkeypatch):
    from virtual_lab.pilots import ms_workflow
    monkeypatch.setattr(ms_workflow,'MAX_SOURCE_BYTES',100)
    normalized,_=ms_workflow.normalize_centroid_csv(b'mz,intensity\n1e-100,1e-100\n')
    assert len(normalized)>100
    assert spectrum_summary(normalized)['peak_count']==1


def test_exported_report_hashes_detect_changed_pdf_and_preserve_existing_files(service,tmp_path):
    from virtual_lab.pilots.reporting import verify_report_files
    source=tmp_path/'synthetic.csv';source.write_text('mz,intensity\n100,1\n')
    obs=service.import_csv(source,experiment_id='exp',sample_id='s',instrument_id='i',operator_id='o',approved_nonconfidential=True)
    output=service.export_report(obs.session_id,tmp_path/'report.pdf')
    checksum=output.with_suffix('.sha256')
    assert verify_report_files(checksum)['files']==['report.json','report.pdf']
    before=output.read_bytes()
    with pytest.raises(ValueError,match='existing'):
        service.export_report(obs.session_id,output)
    assert output.read_bytes()==before
    output.write_bytes(before+b'changed')
    with pytest.raises(ValueError,match='checksum mismatch'):
        verify_report_files(checksum)


@pytest.mark.parametrize('name',['../outside.pdf','/outside.pdf','sub/report.pdf','x\\report.pdf'])
def test_report_checksum_file_cannot_reference_outside_files(tmp_path,name):
    from virtual_lab.pilots.reporting import verify_report_files
    checksum=tmp_path/'report.sha256'
    checksum.write_text('0'*64+'  '+name+'\n')
    with pytest.raises(ValueError): verify_report_files(checksum)
