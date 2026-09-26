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
