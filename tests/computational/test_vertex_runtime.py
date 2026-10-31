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
    with pytest.raises(PermissionError):
        runtime.enable_ai()
    settings = runtime.settings.repository.load().model_dump()
    settings['assistant_enabled'] = True
    runtime.settings.save(settings)
    service = runtime.enable_ai()
    assert service.managed and not runtime.settings.busy
    assert runtime.enable_ai() is service
    runtime.shutdown()
    assert not runtime.settings.busy and runtime.settings._process is None
    runtime.shutdown()
    with pytest.raises(RuntimeError, match='closed'): runtime.enable_ai()


@pytest.mark.parametrize('provider,vertex', [('gemini',False), ('vertex',True)])
def test_provider_selects_the_correct_api_endpoint(monkeypatch, provider, vertex):
    from unittest.mock import MagicMock
    from google import genai
    from virtual_lab.ai import vertex_agents
    client = MagicMock()
    model = MagicMock()
    monkeypatch.setattr(genai, 'Client', client)
    monkeypatch.setattr(vertex_agents, 'GatedGemini', model)
    monkeypatch.setenv('VIRTUALLAB_AI_PROVIDER', provider)
    monkeypatch.setenv('VIRTUALLAB_GEMINI_API_KEY', 'gemini-test-key')
    monkeypatch.setenv('VIRTUALLAB_VERTEX_API_KEY', 'vertex-test-key')
    vertex_agents.get_default_model()
    assert client.call_args.kwargs['vertexai'] is vertex
    assert client.call_args.kwargs['api_key'] == provider+'-test-key'
