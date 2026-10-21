"""Current research UI contract, with no cloud calls or model downloads."""
from unittest.mock import MagicMock

import pytest

from virtual_lab.gui.ai.local_research_workspace import LocalResearchWorkspace, AgentRuntimeWorker
from virtual_lab.gui.shell.workspace_manager import WorkspaceState


@pytest.fixture
def panel(qtbot, monkeypatch):
    monkeypatch.delenv("VIRTUALLAB_VERTEX_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    for name in ('VIRTUALLAB_AI_PROVIDER', 'VIRTUALLAB_GEMINI_API_KEY', 'GEMINI_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    widget = LocalResearchWorkspace(WorkspaceState(), agent_runtime=MagicMock())
    widget.controller = MagicMock()
    qtbot.addWidget(widget)
    yield widget
    assert widget.shutdown_agent_runtime()


def test_unconfigured_research_requires_credentials(panel, monkeypatch):
    assert "credential required" in panel.lbl_egress.text()
    assert not panel.btn_send.isEnabled()
    assert not panel.btn_research.isEnabled()
    start = MagicMock()
    monkeypatch.setattr(panel, "_start_worker", start)
    panel.txt_prompt.setPlainText("Investigate this model")
    panel._on_send()
    start.assert_not_called()


def test_session_key_enables_requests_without_claiming_verification(panel):
    panel.txt_vertex_key.setText("offline-test-key")
    panel._apply_vertex_key()
    assert not panel.txt_vertex_key.text()
    assert panel.btn_send.isEnabled()
    assert "configured; verify" in panel.lbl_egress.text()
    panel.agent_runtime.reset_runner.assert_called_once()


def test_hview_renders_authoritative_identifiers(panel):
    panel.set_hview({"nodes": [{"render_id": "experiment-1", "label": "Experiment", "position": {"x": 0, "y": 0}}]}, "Revision 1")
    assert any("ID: experiment-1" in item.toolTip() for item in panel.hview.scene.items())
    panel.set_hview({}, "Revision 2")
    assert not panel.hview.scene.items()


def test_gemini_session_key_is_separate_from_vertex_and_hidden_after_apply(panel, monkeypatch):
    monkeypatch.setenv('VIRTUALLAB_VERTEX_API_KEY', 'existing-vertex-key')
    panel.provider.setCurrentIndex(panel.provider.findData('gemini'))
    assert not panel.btn_send.isEnabled()
    panel.txt_vertex_key.setText('offline-gemini-key')
    panel._apply_vertex_key()
    import os
    assert os.environ['VIRTUALLAB_AI_PROVIDER'] == 'gemini'
    assert os.environ['VIRTUALLAB_GEMINI_API_KEY'] == 'offline-gemini-key'
    assert os.environ['VIRTUALLAB_VERTEX_API_KEY'] == 'existing-vertex-key'
    assert not panel.txt_vertex_key.text()
    assert 'Gemini API: configured' in panel.lbl_egress.text()
    assert panel.btn_send.isEnabled()
    panel._on_error('Rejected offline-gemini-key')
    assert 'offline-gemini-key' not in panel.lbl_answer.text()
    assert '[REDACTED]' in panel.lbl_answer.text()


def test_reasoning_trace_preserves_order(panel):
    panel._on_step({"type": "USER_REQUEST", "tool": None, "id": "request"})
    panel._on_step({"type": "TOOL_REQUEST", "tool": "device_list", "id": "tool"})
    assert "USER_REQUEST" in panel.lst_trace.item(0).text()
    assert "device_list" in panel.lst_trace.item(1).text()


def test_streamed_answer_keeps_epistemic_labels(panel):
    panel.lbl_answer.clear()
    panel._on_stream_delta("Simulation ")
    panel._on_stream_delta("complete.")
    panel._on_answer("Final summary", ["SIMULATED"])
    assert panel.lbl_answer.text() == "Simulation complete."
    assert panel.lbl_tags.text() == "[SIMULATED]"
    assert "live request succeeded" in panel.lbl_egress.text()
    assert panel.workspace_state.ai_state == "used"


def test_stream_delta_deduplicates_repeated_long_blocks(panel):
    panel.lbl_answer.clear()
    block = "This is a full synthesized scientific critique paragraph from the Director.\n\n"
    panel._on_stream_delta(block)
    panel._on_stream_delta(block)
    assert panel.lbl_answer.text() == block


def test_projects_workflow_status_reflects_ai_state(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(tmp_path))
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.gui.projects_workspace import ProjectsWorkspace

    ws = WorkspaceState()
    ledger = GenesisLedger(str(tmp_path / "genesis.db"))
    try:
        projects = ProjectsWorkspace(ws, ledger)
        qtbot.addWidget(projects)
        pid = projects.service.create_project("Demo")
        projects.service.create_experiment(pid, "Exp", "Question?")
        assert "Manual research:" in projects.workflow_status.text()
        assert "No AI required." in projects.workflow_status.text()

        ws.ai_state = "enabled"
        assert "Optional AI assistance enabled" in projects.workflow_status.text()

        ws.ai_state = "used"
        assert "Optional AI assistance active in this session." in projects.workflow_status.text()
        assert "No AI required." not in projects.workflow_status.text()
    finally:
        projects.service.store.close()
        ledger.conn.close()


@pytest.mark.parametrize("tool,title", [("propose_experiment_branch", "PENDING PROPOSAL"), ("run_simulation", "PENDING ACTION")])
def test_approval_uses_explicit_pending_identity(panel, monkeypatch, tool, title):
    panel._on_approval(object(), {"request-1": tool})
    assert panel.approval_panel.title() == title
    assert "request-1" in panel.lbl_pending.text()
    resume = MagicMock()
    monkeypatch.setattr(panel, "_resume_worker", resume)
    panel._on_approve()
    assert resume.call_args.args[0]["decision"] == "APPROVED"
    assert panel.pending_tool_args == {"proposal_id": "request-1"}


def test_rejection_is_forwarded_as_rejected(panel, monkeypatch):
    panel._on_approval(object(), {"request-1": "run_simulation"})
    resume = MagicMock()
    monkeypatch.setattr(panel, "_resume_worker", resume)
    panel._on_reject()
    assert resume.call_args.args[0]["status"] == "rejected"


def test_quota_error_does_not_claim_a_completed_brief(panel):
    panel._on_error("429 RESOURCE_EXHAUSTED")
    assert "No research brief was completed" in panel.lbl_answer.text()
    assert not panel._vertex_verified


def test_worker_completion_allows_restart(panel, qtbot, monkeypatch):
    def answer(worker, prompt):
        worker.answer_completed.emit(prompt, ["SIMULATED"])
    monkeypatch.setattr(AgentRuntimeWorker, "run_episode", answer)
    for prompt in ("first", "second"):
        panel._start_worker(prompt)
        qtbot.waitUntil(lambda: not panel.agent_thread.isRunning(), timeout=3000)
        assert panel.shutdown_agent_runtime()


def test_running_worker_blocks_second_start_and_shuts_down(panel):
    panel._start_worker()
    first = panel.agent_thread
    panel._start_worker("second")
    assert panel.agent_thread is first
    assert "already running" in panel.lst_trace.item(panel.lst_trace.count()-1).text()
    assert panel.shutdown_agent_runtime()
    assert panel.agent_thread is None


def test_agent_episode_runs_off_gui_thread_and_leaves_ui_responsive(panel, qtbot, monkeypatch):
    import threading
    from PySide6.QtCore import QTimer

    started = threading.Event()
    release = threading.Event()
    worker_threads = []
    main_thread = threading.get_ident()

    def blocking_episode(worker, prompt):
        worker_threads.append(threading.get_ident())
        started.set()
        release.wait(3)
        worker.answer_completed.emit('Offline worker check', ['SIMULATED'])

    monkeypatch.setattr(AgentRuntimeWorker, 'run_episode', blocking_episode)
    ticks = []
    timer = QTimer(panel)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(10)
    try:
        panel._start_worker('Offline responsiveness check')
        qtbot.waitUntil(started.is_set)
        qtbot.waitUntil(lambda: len(ticks) >= 3)
        assert len(worker_threads) == 1
        assert worker_threads[0] != main_thread
    finally:
        release.set()
        timer.stop()
        assert panel.shutdown_agent_runtime()


def test_citation_controls_survive_added_runs_and_ai_status_changes(qtbot, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAccessible
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.gui.projects_workspace import ProjectsWorkspace
    from virtual_lab.gui.services.experiment_controller import ExperimentController

    ws = WorkspaceState()
    ledger = GenesisLedger(str(tmp_path / 'genesis.db'))
    projects = ProjectsWorkspace(ws, ledger)
    qtbot.addWidget(projects)
    try:
        pid = projects.service.create_project('Citation accessibility')
        projects.service.create_experiment(pid, 'Three runs', 'Which results support the conclusion?')
        controller = ExperimentController(ws)
        failures = []
        controller.runFailed.connect(failures.append)
        first_box = None
        for exposure in (1, 2, 5):
            controller.run_experiment(dict(model_id='gene_expression', concentration_um=exposure,
                duration_h=1, members=2))
            qtbot.waitUntil(lambda: controller.worker is None)
            assert not failures, failures
            if first_box is None:
                first_box = projects.evidence_choices.itemWidget(projects.evidence_choices.item(0))
                first_box.setChecked(True)
            else:
                assert projects.evidence_choices.itemWidget(projects.evidence_choices.item(0)) is first_box
        ws.ai_state = 'used'
        assert projects.evidence_choices.count() == 3
        assert first_box.isChecked()
        boxes = [projects.evidence_choices.itemWidget(row) for row in projects.evidence_choices.rows]
        assert len({box.objectName() for box in boxes}) == 3
        for box in boxes:
            interface = QAccessible.queryAccessibleInterface(box)
            assert interface.role() == QAccessible.CheckBox
            assert interface.text(QAccessible.Name) == box.text()
        boxes[-1].setChecked(True)
        assert projects.evidence_choices.item(2).checkState() == Qt.Checked
        # Switching experiment clears selections instead of leaking prior citations.
        projects.service.create_experiment(pid, 'New study', 'New question')
        assert projects.evidence_choices.count() == 0
    finally:
        projects.service.store.close()
        ledger.conn.close()
