"""Exercise the real offline navigation, persisted views and scope boundaries."""

import hashlib
import json
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from virtual_lab.pilots.desktop import MSPilotWindow


def create(nav, name):
    nav.show_library("mass_spectrometry")
    nav.new_name.setText(name)
    nav.create_project()
    return nav.project_id


def experiment(window, name):
    panel = window.projects
    panel.experiment_name.setText(name)
    panel.question.setText("Synthetic workflow scope test")
    panel._create_experiment()
    return window.workspace.active_experiment.id


def scan(window, tmp_path, name, mz):
    panel = window.ms_pilot
    source = tmp_path / (name + ".csv")
    source.write_text(f"mz,intensity\n{mz},8\n{mz+1},4\n")
    for key, value in {
        "source": str(source),
        "dataset_id": name,
        "sample_id": "synthetic",
        "instrument_id": "synthetic",
        "operator_id": "test",
    }.items():
        panel.fields[key].setText(value)
    panel.approval.setChecked(True)
    panel.data_origin.setCurrentIndex(panel.data_origin.findData("synthetic"))
    panel.validate_input()
    assert panel.validated is not None, panel.status.text()
    panel.finalize_import()
    assert panel.selected_run, panel.status.text()
    return panel.selected_run


def test_home_library_ms_project_and_unavailable_tools(qtbot):
    window = MSPilotWindow()
    qtbot.addWidget(window)
    nav = window.navigation
    assert nav.stack.currentWidget() is nav.home
    assert not nav.domain_buttons["physics_simulation"].isEnabled()
    qtbot.mouseClick(nav.domain_buttons["mass_spectrometry"], Qt.LeftButton)
    assert nav.stack.currentWidget() is nav.library
    nav.new_name.setText("MS study")
    nav.create_project()
    assert nav.stack.currentWidget() is nav.workstation
    assert (
        window.workspace.active_project_id == nav.project_id
        and window.workspace.active_experiment is None
    )
    assert window.tabs.currentWidget() is window.ms_pilot
    assert "Mass Spectrometry / MS study" in nav.breadcrumb.text()
    with pytest.raises(ValueError, match="unavailable"):
        nav.open_tool("simulation")
    assert not window.intent_panel.learning.isChecked()
    assert all(
        not button.isEnabled() for button in window.projects.navigation_buttons.values()
    )
    assert "provenance" in nav.tools
    window.close()


def test_two_projects_experiments_datasets_views_and_restart(qtbot, tmp_path):
    window = MSPilotWindow()
    qtbot.addWidget(window)
    nav = window.navigation
    a = create(nav, "Alpha")
    e1 = experiment(window, "Alpha first")
    r1 = scan(window, tmp_path, "alpha1", 100)
    window.ms_pilot.tabs.setCurrentIndex(2)
    e2 = experiment(window, "Alpha second")
    r2 = scan(window, tmp_path, "alpha2", 200)
    window.ms_pilot.tabs.setCurrentIndex(3)
    nav.experiments.setCurrentIndex(nav.experiments.findData(e1))
    nav.open_experiment()
    assert (
        window.ms_pilot.selected_run == r1 and window.ms_pilot.tabs.currentIndex() == 2
    )
    nav.open_tool("intent")
    b = create(nav, "Beta")
    e3 = experiment(window, "Beta only")
    assert (
        window.ms_pilot.datasets.count() == 0 and window.ms_pilot.selected_run is None
    )
    assert (
        window.ms_pilot.fields["source"].text() == ""
        and not window.ms_pilot.approval.isChecked()
    )
    assert (
        window.workspace.current_result is None
        and window.intent_panel.models.count() == 0
    )
    nav.open_project(a)
    assert (
        window.workspace.active_experiment.id == e1
        and window.tabs.currentWidget() is window.intent_panel
    )
    assert (
        window.ms_pilot.selected_run == r1 and window.ms_pilot.tabs.currentIndex() == 2
    )
    assert "100,8" in window.ms_pilot.original.toPlainText()
    assert "200,8" not in window.ms_pilot.original.toPlainText()
    nav.open_tool("ms_workflow")
    window.close()
    reopened = MSPilotWindow()
    qtbot.addWidget(reopened)
    assert (
        reopened.workspace.active_project_id == a
        and reopened.workspace.active_experiment.id == e1
    )
    assert reopened.tabs.currentWidget() is reopened.ms_pilot
    assert (
        reopened.ms_pilot.selected_run == r1
        and reopened.ms_pilot.tabs.currentIndex() == 2
    )
    reopened.navigation.experiments.setCurrentIndex(
        reopened.navigation.experiments.findData(e2)
    )
    reopened.navigation.open_experiment()
    assert (
        reopened.ms_pilot.selected_run == r2
        and reopened.ms_pilot.tabs.currentIndex() == 3
    )
    assert len(reopened.projects.service.store.get_observations_for_experiment(e3)) == 0
    reopened.close()


def test_library_search_move_and_home_are_durable(qtbot):
    window = MSPilotWindow()
    qtbot.addWidget(window)
    nav = window.navigation
    a = create(nav, "Alpha")
    b = create(nav, "Beta")
    nav.show_library("mass_spectrometry")
    nav.library_search.setText("alpha")
    assert nav.project_list.count() == 1
    nav.project_list.setCurrentRow(0)
    nav.move_domain.setCurrentIndex(nav.move_domain.findData("general"))
    nav.move_project()
    assert nav.project_list.count() == 0
    nav.show_home()
    nav.home_search.setText("Alpha")
    assert nav.recent.count() == 1
    nav.show_library("general")
    assert nav.project_list.count() == 1
    window.close()
    reopened = MSPilotWindow()
    qtbot.addWidget(reopened)
    assert reopened.navigation.stack.currentWidget() is reopened.navigation.library
    assert (
        reopened.navigation.domain_id == "general"
        and reopened.workspace.active_experiment is None
    )
    reopened.close()


def test_same_core_academia_profile_and_switch_guard(qtbot):
    window = MSPilotWindow(profile="academia")
    qtbot.addWidget(window)
    nav = window.navigation
    assert nav.profile.title == "VirtualLab Academia"
    project = create(nav, "Teaching study")
    exp = experiment(window, "Modeled exercise")
    nav.can_switch = lambda: False
    with pytest.raises(ValueError, match="Finish or cancel"):
        nav.show_home()
    assert window.workspace.active_experiment.id == exp and nav.project_id == project
    assert window.projects.service.projects()[0]["domain_id"] == "mass_spectrometry"
    nav.can_switch = lambda: True
    window.close()


def test_tampered_saved_dataset_never_restores_prior_spectrum(qtbot, tmp_path):
    window = MSPilotWindow()
    qtbot.addWidget(window)
    a = create(window.navigation, "A")
    experiment(window, "First")
    run = scan(window, tmp_path, "tamper-test", 100)
    path = window.ms_pilot.service.manifest_path(run).parent / "source.csv"
    path.write_bytes(path.read_bytes() + b"changed")
    window.close()
    reopened = MSPilotWindow()
    qtbot.addWidget(reopened)
    assert reopened.ms_pilot.selected_run is None
    assert reopened.ms_pilot.original.toPlainText() == ""
    assert "INTEGRITY" in reopened.ms_pilot.status.text()
    reopened.close()


def test_stale_dataset_selection_is_refused_before_reading(qtbot, tmp_path):
    from PySide6.QtWidgets import QListWidgetItem

    window = MSPilotWindow()
    qtbot.addWidget(window)
    a = create(window.navigation, "A")
    experiment(window, "A experiment")
    run = scan(window, tmp_path, "source-a", 100)
    b = create(window.navigation, "B")
    experiment(window, "B experiment")
    stale = QListWidgetItem("Stale selection")
    stale.setData(Qt.UserRole, run)
    window.ms_pilot.select_dataset(stale)
    assert (
        window.ms_pilot.selected_run is None
        and window.ms_pilot.original.toPlainText() == ""
    )
    assert "DATASET_SCOPE" in window.ms_pilot.status.text()
    assert window.intent_panel.project_id() == b
    window.close()


def test_empty_project_switch_clears_uncommitted_ms_intake(qtbot):
    window = MSPilotWindow()
    qtbot.addWidget(window)
    create(window.navigation, "Empty A")
    window.ms_pilot.fields["source"].setText("/previous-project-file.csv")
    window.ms_pilot.data_origin.setCurrentIndex(
        window.ms_pilot.data_origin.findData("public_reference")
    )
    window.ms_pilot.approval.setChecked(True)
    create(window.navigation, "Empty B")
    assert window.workspace.active_experiment is None
    assert window.ms_pilot.fields["source"].text() == ""
    assert window.ms_pilot.data_origin.currentData() == "unspecified"
    assert not window.ms_pilot.approval.isChecked()
    window.close()


def test_spectrum_and_summary_fit_an_ordinary_workstation(qtbot, tmp_path):
    from PySide6.QtWidgets import QScrollArea

    window = MSPilotWindow()
    qtbot.addWidget(window)
    create(window.navigation, "Spectrum overview")
    experiment(window, "Overview")
    scan(window, tmp_path, "overview", 100)
    window.ms_pilot.tabs.setCurrentIndex(1)
    window.resize(1400, 850)
    window.show()
    qtbot.waitUntil(lambda: window.ms_pilot.plot.isVisible())
    panel = window.ms_pilot
    qtbot.waitUntil(
        lambda: panel.summary.geometry().bottom()
        < panel.summary.parentWidget().height()
    )
    assert panel.plot.geometry().bottom() < panel.plot.parentWidget().height()
    for scroll in panel.tabs.widget(1).findChildren(QScrollArea):
        if scroll.isVisible():
            assert scroll.verticalScrollBar().maximum() == 0
    window.close()


def test_library_import_opens_portable_project_without_dummy_project(
    qtbot, tmp_path, monkeypatch
):
    source = MSPilotWindow()
    qtbot.addWidget(source)
    project = create(source.navigation, "Portable project")
    exp = experiment(source, "Portable spectrum")
    scan(source, tmp_path, "portable-spectrum", 100)
    package = source.projects.service.export_study(tmp_path / "portable.vlab-study")
    source.close()
    recipient = tmp_path / "recipient"
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(recipient))
    window = MSPilotWindow()
    qtbot.addWidget(window)
    nav = window.navigation
    assert not window.projects.service.projects()
    nav.show_library("mass_spectrometry")
    nav.study_path.setText(str(package))
    nav.import_project()
    assert len(window.projects.service.projects()) == 1
    assert nav.project_id == project and nav.domain_id == "mass_spectrometry"
    assert (
        window.workspace.active_experiment.id == exp
        and window.ms_pilot.datasets.count() == 1
    )
    window.ms_pilot.datasets.setCurrentRow(0)
    assert window.ms_pilot.selected_run is not None
    assert (
        window.projects.service.store.get_observations_for_experiment(exp)[
            0
        ].epistemic_state.value
        == "UNKNOWN"
    )
    window.close()
