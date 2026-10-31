"""Notebook actions must respect the same active-work guard as navigation."""

import pytest
from PySide6.QtWidgets import QPushButton
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.gui.projects_workspace import ProjectsWorkspace
from virtual_lab.gui.services.study_service import StudyService
from virtual_lab.gui.shell.workspace_manager import WorkspaceState


@pytest.fixture
def notebook(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(tmp_path))
    ledger = GenesisLedger(str(tmp_path / "genesis.db"))
    panel = ProjectsWorkspace(WorkspaceState(), ledger)
    qtbot.addWidget(panel)
    project = panel.service.create_project("Guarded project")
    first = panel.service.create_experiment(project, "First", "First question")
    second = panel.service.create_experiment(project, "Second", "Second question")
    panel.service.activate(first)
    panel.refresh_projects(project)
    panel.experiments.setCurrentIndex(panel.experiments.findData(second))
    panel.experiment_name.setText("Must not be created while busy")
    panel.question.setText("Does the guard run before persistence?")
    yield panel, first, second, tmp_path
    panel.service.store.close()
    ledger.conn.close()


def button(panel, title):
    matches = [b for b in panel.findChildren(QPushButton) if b.text() == title]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize(
    "title",
    [
        "Create and open experiment",
        "Open experiment",
        "Return to unassigned staging",
    ],
)
def test_notebook_context_buttons_block_before_changes(notebook, title):
    panel, first, _, _ = notebook
    panel.context_switch_allowed = lambda: False
    rows = panel.service.store.list_experiments()
    events = panel.service.ledger.conn.execute(
        "SELECT COUNT(*) FROM ledger_events"
    ).fetchone()[0]
    button(panel, title).click()
    assert panel.workspace.active_experiment.id == first
    assert panel.service.store.list_experiments() == rows
    assert (
        panel.service.ledger.conn.execute(
            "SELECT COUNT(*) FROM ledger_events"
        ).fetchone()[0]
        == events
    )
    assert "Finish or cancel" in panel.status.text()


def test_context_actions_work_again_after_work_finishes(notebook):
    panel, first, second, _ = notebook
    panel.context_switch_allowed = lambda: False
    with pytest.raises(ValueError, match="Finish or cancel"):
        panel._create_experiment()
    panel.context_switch_allowed = lambda: True
    button(panel, "Open experiment").click()
    assert panel.workspace.active_experiment.id == second
    button(panel, "Return to unassigned staging").click()
    assert panel.workspace.active_experiment is None
    assert panel.workspace.active_project_id is None
    button(panel, "Create and open experiment").click()
    assert panel.workspace.active_experiment.id not in (first, second)
    assert len(panel.service.store.list_experiments()) == 3


def test_notebook_import_guard_precedes_reads_and_persistence(notebook):
    panel, first, _, root = notebook
    foreign_ledger = GenesisLedger(str(root / "foreign-ledger.db"))
    foreign_store = ExperimentStore(str(root / "foreign-experiments.db"))
    foreign = StudyService(WorkspaceState(), foreign_ledger, foreign_store)
    try:
        project = foreign.create_project("Imported project", "data_analysis")
        experiment = foreign.create_experiment(
            project, "Imported experiment", "Question"
        )
        package = foreign.export_study(root / "import.vlab-study")
    finally:
        foreign_store.close()
        foreign_ledger.conn.close()
    panel.package_path.setText(str(package))
    panel.context_switch_allowed = lambda: False
    before = panel.service.projects()
    button(panel, "Import study package").click()
    assert panel.workspace.active_experiment.id == first
    assert panel.service.projects() == before
    assert panel.service.store.get_experiment(experiment) is None
    assert "Finish or cancel" in panel.status.text()
    panel.context_switch_allowed = lambda: True
    button(panel, "Import study package").click()
    assert panel.workspace.active_experiment.id == experiment
    assert panel.workspace.active_project_id == project
    assert "Study imported" in panel.status.text()
