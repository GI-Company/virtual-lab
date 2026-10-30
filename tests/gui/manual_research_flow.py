"""Executable smoke scenario with every AI import blocked."""
import csv
import importlib.abc
import json
import os
from pathlib import Path
import sys
import time


class NoAI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'virtual_lab.ai' or fullname.startswith(('virtual_lab.ai.', 'google.adk', 'google.genai', 'mlx_lm')):
            raise ImportError('AI is intentionally unavailable: ' + fullname)


sys.meta_path.insert(0, NoAI())

from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QPushButton
from virtual_lab.gui.shell.main_window import VirtualLabApplication
from virtual_lab.domain.epistemics import EpistemicState


def wait_for(app, condition, description):
    deadline = time.monotonic() + 20
    while not condition():
        app.processEvents()
        time.sleep(.005)
        if time.monotonic() > deadline:
            raise AssertionError(description)
    app.processEvents()


def close_window(app, window):
    window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def main(root):
    root = Path(root)
    source, recipient = root/'source', root/'recipient'
    os.environ['VIRTUALLAB_DATA_DIR'] = str(source)
    os.environ.pop('VIRTUALLAB_VERTEX_API_KEY', None)
    os.environ.pop('GOOGLE_CLOUD_PROJECT', None)
    os.environ.pop('VIRTUALLAB_RUN_LIVE_AI_TESTS', None)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = VirtualLabApplication()
    from virtual_lab.version import __version__
    assert window.windowTitle() == f"VirtualLab v{__version__} - Scientific Cockpit"
    assert window.tabs.tabText(0) == 'Projects'
    assert {'Projects', 'MS Workflow', 'Simulation', 'Evidence', 'Provenance'} <= {
        window.tabs.tabText(i) for i in range(window.tabs.count())}
    assert window.ai_enable_button.isEnabled()
    if '--shell-only' in sys.argv:
        assert window.runtime.agent_runtime is None and not window.runtime.gateway.server.isListening()
        close_window(app, window)
        print('shell passed without AI')
        return
    if os.environ.get('VIRTUALLAB_FLOW_SCREENSHOTS'):
        window.show()
    panel = window.projects
    assert window.runtime.agent_runtime is None and window.local_research is None
    assert not window.runtime.gateway.server.isListening()
    panel.project_name.setText('Independent gene-expression study')
    next(b for b in panel.findChildren(QPushButton) if b.text() == 'Create project').click()
    panel.experiment_name.setText('Induction and control')
    panel.question.setText('Under the assumed model, does exposure increase protein abundance at one hour?')
    next(b for b in panel.findChildren(QPushButton) if b.text() == 'Create and open experiment').click()
    exp_id = window.workspace.active_experiment.id
    fields = dict(hypothesis='Exposure increases modeled protein abundance.', method='Compare zero and five micromolar exposures with identical fixed rates, seed and duration.',
                  expected_outcome='Higher median protein in the exposure scenario.', acceptance_criteria='Compare final protein medians at one hour; interpret within this uncalibrated model only.')
    for key, value in fields.items(): panel.plan_fields[key].setPlainText(value)
    panel.save_plan_button.click()
    assert len(panel.service.research_records()) == 1, panel.status.text()
    next(b for b in panel.findChildren(QPushButton) if b.text() == 'Open Simulation').click()
    assert window.tabs.currentWidget() is window.experiment
    simulation = window.experiment
    simulation.model_selector.setCurrentIndex(simulation.model_selector.findData('gene_expression'))
    simulation.fields['duration_h'].setValue(1)
    simulation.fields['variation'].setValue(0)
    simulation.spn_ensemble.setValue(4)
    for concentration in (0, 5):
        simulation.fields['concentration_um'].setValue(concentration)
        simulation.btn_run.click()
        wait_for(app, lambda: simulation.controller.worker is None, simulation.status.text())
        assert window.workspace.current_result is not None, simulation.status.text()
    observations = panel.service.store.get_observations_for_experiment(exp_id)
    simulations = [o for o in observations if o.instrument_id == 'simulation']
    assert len(simulations) == 2
    assert simulation.btn_open_compare.isEnabled()
    simulation.btn_open_compare.click()
    assert window.tabs.currentWidget() is window.compare
    window.compare.refresh()
    window.compare.left.setCurrentIndex(0); window.compare.right.setCurrentIndex(1)
    assert window.compare.table.rowCount() == 2, window.compare.note.text()
    assert float(window.compare.table.item(1, 4).text()) > 0
    window.compare.btn_numerical.click()
    assert window.tabs.currentWidget() is window.numerical
    assert window.numerical.lbl_status.text() == 'PASSED'
    window.numerical.btn_conclusion.click()
    assert window.tabs.currentWidget() is window.projects
    assert panel.notebook.currentIndex() == 2
    for i in range(panel.results.count()):
        if panel.results.item(i).data(Qt.UserRole).observation_id == simulations[-1].observation_id:
            panel.results.setCurrentRow(i)
    assert window.analysis.list_endpoints.count() == 2
    csv_path = root/'protein-trajectories.csv'
    panel.csv_path.setText(str(csv_path)); panel.csv_export_button.click()
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 97*2*2
    assert {r['scenario'] for r in rows} == {'control', 'exposure'}
    assert {r['epistemic_state'] for r in rows} == {'SIMULATED'}
    panel.interpretation.setPlainText('The exposure scenario has a higher final protein median in this model.')
    panel.limitations.setPlainText('Generic assumed kinetics and fixed parameters; no measured-data or biological validation.')
    panel.decision.setCurrentIndex(panel.decision.findData('supports_within_scope'))
    for i in range(panel.evidence_choices.count()):
        item = panel.evidence_choices.item(i)
        checkbox = panel.evidence_choices.itemWidget(item)
        assert checkbox.accessibleName().startswith('simulation · SIMULATED')
        checkbox.click()
        assert item.checkState() == Qt.Checked
    panel.save_conclusion_button.click()
    records = panel.service.research_records()
    assert len(records) == 2, panel.status.text()
    assert records[-1][0].epistemic_state == EpistemicState.INFERRED
    assert len(records[-1][1]['result_refs']) == 2
    assert records[-1][1]['planning_scope'] == 'before_selected_results'
    if os.environ.get('VIRTUALLAB_FLOW_SCREENSHOTS'):
        panel.notebook.setCurrentIndex(2)
        app.processEvents()
        window.grab().save(str(root/'manual-research.png'))
    bundle = root/'manual.vlab-study'
    panel.package_path.setText(str(bundle)); panel._export()
    assert bundle.exists(), panel.status.text()
    close_window(app, window)
    elsewhere = root/'different-launch-directory'; elsewhere.mkdir()
    os.chdir(elsewhere)
    reopened = VirtualLabApplication()
    assert reopened.workspace.active_experiment.id == exp_id
    assert len(reopened.projects.service.research_records()) == 2
    assert reopened.projects.plan_fields['hypothesis'].toPlainText() == fields['hypothesis']
    assert not (elsewhere/'.virtuallab').exists()
    close_window(app, reopened)
    os.environ['VIRTUALLAB_DATA_DIR'] = str(recipient)
    imported = VirtualLabApplication()
    imported.projects.package_path.setText(str(bundle)); imported.projects._import()
    assert imported.workspace.active_experiment.id == exp_id, imported.projects.status.text()
    assert 'Imported study verified (4 records: 1 plan, 2 simulation, 1 conclusion · 0 local runs)' in imported.ledger_status.text()
    assert 'Imported study package verified' in imported.provenance.status.text()
    assert len(imported.projects.service.research_records()) == 2
    for obs in imported.projects.service.store.get_observations_for_experiment(exp_id):
        imported.projects.service.inspect(obs)
        assert Path(obs.artifact_path).is_relative_to(recipient)
    assert imported.runtime.agent_runtime is None and imported.local_research is None
    imported.ai_enable_button.click()
    assert 'not installed' in imported.ai_status.text()
    assert imported.runtime.agent_runtime is None
    assert not any(name.startswith(('virtual_lab.ai', 'google.adk', 'google.genai')) for name in sys.modules)
    close_window(app, imported)
    app.processEvents()
    print(json.dumps({'status':'passed','flow':'plan → run → compare → CSV → conclusion → study → restart → import', 'ai_imports':0}))


if __name__ == '__main__':
    main(sys.argv[1])
