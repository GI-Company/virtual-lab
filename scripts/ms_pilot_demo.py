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
    source = Path(__file__).resolve().parents[1]/'tests/fixtures/ms-pilot/synthetic-centroids.csv'
    metadata = dict(pilot_id='mild-biotec-initial-ms', dataset_id='synthetic-001', sample_id='synthetic-protein-001',
                    instrument_id='synthetic-ms', operator_id='demo-reviewer', approved_nonconfidential=True)
    obs = panel.service.import_csv(source, experiment_id=exp, **metadata)
    panel.service.reprocess(obs.session_id)
    panel.service.review(obs.session_id, reviewer='demo-reviewer', approved=True, note='Synthetic workflow checks only; no scientific validation.')
    for suffix in ('json', 'pdf'):
        panel.service.export_report(obs.session_id, output/('ms-workflow-report.'+suffix))
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
    window.close()
    print(output)


if __name__ == '__main__':
    main()
