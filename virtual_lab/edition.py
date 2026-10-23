"""Edition presentation defaults. These are not authorization boundaries."""
import json
import os
from pathlib import Path

EDITIONS = {'researcher': 'Researcher', 'high-school': 'High School',
            'undergraduate': 'Undergraduate', 'graduate': 'Graduate'}

def current_edition():
    selected = os.environ.get('VIRTUALLAB_EDITION')
    if selected is None:
        selected = json.loads(Path(__file__).with_name('beta_edition.json').read_text())['edition']
    if selected not in EDITIONS:
        raise ValueError('Unknown VirtualLab edition: ' + selected)
    return selected

def configure_window(window):
    edition = current_edition()
    window.setWindowTitle(window.windowTitle() + ' — ' + EDITIONS[edition] + ' beta')
    from PySide6.QtWidgets import QLabel
    from virtual_lab.core.paths import app_data_dir
    guide = {
        'researcher': 'Researcher beta: inspect assumptions and numerical checks before drawing conclusions.',
        'high-school': 'Guided lab: write your question and prediction, run two exposures, compare the curves, then explain your evidence in your own words.',
        'undergraduate': 'Teaching lab: document your hypothesis, controls and parameter assumptions; compare results, verify numerics, cite evidence and export your report.',
        'graduate': 'Graduate lab: document model selection, uncertainty and limitations; connect predictions to independently collected evidence.'}[edition]
    label = QLabel(guide + '\nBeta workspace: ' + str(app_data_dir()))
    label.setWordWrap(True)
    window.centralWidget().layout().insertWidget(1, label)
    window.edition = edition
    if edition in ('high-school', 'undergraduate'):
        hidden = [window.world, window.biological, window.instruments, window.computational]
        if edition == 'high-school':
            hidden += [window.calibration_tabs, window.ai_panel]
            window.ai_enable_button.setEnabled(False)
            window.btn_ai_drawer.setEnabled(False)
        for widget in hidden:
            window.tabs.setTabVisible(window.tabs.indexOf(widget), False)
        panel = window.experiment
        panel.model_selector.setCurrentIndex(panel.model_selector.findData('gene_expression'))
        panel.fields['duration_h'].setValue(24)
        if edition == 'high-school':
            panel.model_selector.setEnabled(False)
            panel.model_group.setEnabled(False)
            panel.seed.setEnabled(False)
            panel.cmb_backend.setEnabled(False)
            panel.model_import_button.setEnabled(False)
