"""Full desktop integration: navigation -> runs -> scope -> restart, AI unavailable."""

import json
import os
from pathlib import Path
import sys
from manual_research_flow import NoAI, wait_for, close_window
from PySide6.QtWidgets import QApplication, QPushButton
from virtual_lab.gui.shell.main_window import VirtualLabApplication


def main(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    os.environ["VIRTUALLAB_DATA_DIR"] = str(root / "workspace")
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = VirtualLabApplication()
    window.show()
    nav = window.navigation
    study = window.projects.service
    assert nav.stack.currentWidget() is nav.home

    def capture(name):
        app.processEvents()
        if "--screenshots" in sys.argv:
            window.grab().save(str(root / (name + ".png")))

    capture("01-home")

    def create(name):
        nav.show_library("physics_simulation")
        nav.new_name.setText(name)
        nav.create_project()
        window.projects.experiment_name.setText(name + " experiment")
        window.projects.question.setText(
            "Synthetic software comparison, not laboratory validation"
        )
        window.projects._create_experiment()
        return nav.project_id, window.workspace.active_experiment.id

    a, ea = create("Alpha scope")
    capture("02-alpha-workstation")
    window.experiment.controller.run_experiment(
        dict(model_id="gene_expression", duration_h=1, members=2)
    )
    wait_for(
        app, lambda: window.experiment.controller.worker is None, "First simulation"
    )
    assert window.workspace.current_result is not None
    ra = study.store.get_observations_for_experiment(ea)[0]
    window.projects.refresh_results()
    window.projects.results.setCurrentRow(0)
    nav.open_tool("analysis")
    assert window.analysis.result is not None
    b, eb = create("Beta scope")
    assert (
        window.analysis.result is None
        and window.numerical.lbl_status.text() == "NOT RUN"
    )
    assert (
        window.compare.left.count() == 0
        and window.provenance.inspector.toPlainText() == ""
    )
    window.experiment.controller.run_experiment(
        dict(model_id="gene_expression", duration_h=1, members=2, concentration_um=5)
    )
    wait_for(
        app, lambda: window.experiment.controller.worker is None, "Second simulation"
    )
    rb = study.store.get_observations_for_experiment(eb)[0]
    window.compare.refresh()
    assert window.compare.left.count() == 1
    assert set(window.compare.runs) == {rb.observation_id}
    window.provenance.refresh()
    assert all(
        e["payload"].get("experiment_id") != ea
        and e["payload"].get("project_id") != a
        and e["payload"].get("run_id") != ra.session_id
        for e in window.provenance.events
    )
    assert any(
        e["payload"].get("run_id") == rb.session_id for e in window.provenance.events
    )
    assert window.ledger_status.text() == "1 saved simulation runs verified"
    capture("03-beta-scoped-results")
    nav.open_project(a)
    assert window.workspace.active_experiment.id == ea
    assert window.tabs.currentWidget() is window.analysis
    assert window.analysis.result is not None
    assert set(window.compare.runs) == {ra.observation_id}
    assert window.workspace.current_result.run_id == ra.session_id
    capture("04-alpha-restored")
    close_window(app, window)
    window = VirtualLabApplication()
    window.show()
    nav = window.navigation
    assert (
        window.workspace.active_experiment.id == ea
        and window.tabs.currentWidget() is window.analysis
    )
    assert window.analysis.result is not None
    assert window.workspace.current_result.run_id == ra.session_id
    nav.open_tool("instruments")
    assert not window.runtime.gateway.server.isListening()
    close_window(app, window)
    window = VirtualLabApplication()
    window.show()
    nav = window.navigation
    assert window.tabs.currentWidget() is window.instruments
    assert (
        not window.runtime.gateway.server.isListening()
        and window.runtime.agent_runtime is None
    )
    assert window.start_listener_button.isEnabled()
    assert not window.intent_panel.learning.isChecked()
    nav.open_tool("assistant")
    assert window.runtime.agent_runtime is None
    nav.show_home()
    capture("05-home-with-recent")
    close_window(app, window)
    print(
        json.dumps(
            {
                "status": "passed",
                "projects": 2,
                "simulations": 2,
                "scope": "Compare, provenance, analysis, notebook and restored views",
                "restart": "analysis and instruments",
                "automatic_ai_or_hardware_activation": False,
            }
        )
    )


if __name__ == "__main__":
    main(sys.argv[1])
