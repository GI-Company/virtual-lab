"""Current research UI contract, with no cloud calls or model downloads."""
from unittest.mock import MagicMock

import pytest

from virtual_lab.gui.ai.local_research_workspace import LocalResearchWorkspace, AgentRuntimeWorker
from virtual_lab.gui.shell.workspace_manager import WorkspaceState


@pytest.fixture
def panel(qtbot, monkeypatch):
    monkeypatch.delenv("VIRTUALLAB_VERTEX_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
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
