"""Generate local synthetic workflow evidence and reports; never uses lab data."""
import argparse
import json
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from virtual_lab.pilots.desktop import MSPilotWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory for demo data and reports')
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.environ['VIRTUALLAB_DATA_DIR'] = str(output/'local-data')
    app = QApplication([])
    window = MSPilotWindow()
    service = window.projects.service
    project = service.create_project('Synthetic MS workflow pilot')
    exp = service.create_experiment(project, 'Centroid CSV intake', 'Can approved centroid data be preserved, traced and reprocessed?')
    panel = window.ms_pilot
    source = Path(__file__).resolve().parents[1]/'tests/fixtures/ms-pilot/synthetic-inspection-spectrum.csv'
    metadata = dict(data_origin='synthetic', pilot_id='mild-biotec-initial-ms', dataset_id='synthetic-inspection-001', sample_id='synthetic-spectrum-001',
                    instrument_id='synthetic-ms', operator_id='demo-reviewer', approved_nonconfidential=True)
    obs = panel.service.import_csv(source, experiment_id=exp, **metadata)
    panel.service.reprocess(obs.session_id)
    panel.service.test_alteration(obs.session_id)
    panel.service.review(obs.session_id, reviewer='demo-reviewer', approved=True, note='Synthetic workflow checks only; no scientific validation.')
    panel.service.export_report(obs.session_id, output/'ms-workflow-report.pdf')
    (output/'export-receipt.json').write_text(json.dumps(panel.service.events(obs.session_id)[-1],indent=2)+'\n')
    service.export_study(output/'synthetic-ms.vlab-study')
    panel.refresh()
    panel.datasets.setCurrentRow(0)
    panel.tabs.setCurrentIndex(1)
    window.tabs.setCurrentWidget(panel)
    window.show()
    app.processEvents()
    window.grab().save(str(output/'ms-workflow-desktop.png'))
    (output/'demo-result.json').write_text(json.dumps({'run_id':obs.session_id,
        'verification':panel.service.verify(obs.session_id), 'data_kind':'synthetic-only'},indent=2)+'\n')
    import platform
    from virtual_lab.version import __version__
    (output/'environment.json').write_text(json.dumps({'application_version':__version__, 'python':platform.python_version(),
        'platform':platform.platform(), 'source_kind':'committed synthetic fixture', 'processing_version':'centroid-decimal-sort-v2'},indent=2)+'\n')
    import shutil
    evidence = output/'evidence'
    evidence.mkdir()
    for name in ('source.csv','peaks.csv','manifest.json'):
        shutil.copyfile(Path(obs.artifact_path).parent/name, evidence/name)
    window.close()
    print(output)


if __name__ == '__main__':
    main()
