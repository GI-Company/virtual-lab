import pytest

pytest.importorskip("google.adk", reason="Optional ai extra is not installed")

def test_vertex_initialization_is_lazy_and_refreshes_after_key_change(monkeypatch):
    from virtual_lab.ai import runtime_service
    calls = []
    def create(session_service):
        runner = object()
        calls.append(runner)
        return runner
    monkeypatch.setattr(runtime_service, "create_virtual_lab_runner", create)
    monkeypatch.delenv("VIRTUALLAB_VERTEX_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    runtime = runtime_service.AgentRuntimeService()
    try:
        assert not calls
        first = runtime.runner
        assert runtime.runner is first
        runtime.reset_runner()
        assert runtime.runner is not first
        assert len(calls) == 2
    finally:
        runtime.shutdown()


def test_ai_is_enabled_explicitly_and_shuts_down(qapp):
    from virtual_lab.core.runtime import create_virtual_lab_runtime
    runtime = create_virtual_lab_runtime()
    assert runtime.agent_runtime is None
    assert not runtime.gateway.server.isListening()
    service = runtime.enable_ai()
    assert service._runner is None
    assert runtime.enable_ai() is service
    runtime.shutdown()
    assert not service.thread.is_alive()
    runtime.shutdown()
    with pytest.raises(RuntimeError, match='closed'): runtime.enable_ai()
