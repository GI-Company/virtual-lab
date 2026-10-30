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
    a = export_report(report, tmp_path/'one.json')
    b = export_report(build_report(manifest), tmp_path/'two.json')
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
