"""Cloud adapter selection is verified with mocks, never real credentials."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from virtual_lab.settings.worker import run

@pytest.mark.parametrize('kind,expected', [('gemini',False),('vertex',True)])
def test_cloud_adapter_explicit_selection_no_tools(monkeypatch,kind,expected):
    client=Mock(); client.models.generate_content.return_value.text='OK'
    factory=Mock(return_value=client)
    monkeypatch.setitem(sys.modules,'google.genai',SimpleNamespace(Client=factory))
    monkeypatch.setitem(sys.modules,'google',SimpleNamespace(genai=SimpleNamespace(Client=factory)))
    request={'provider':{'kind':kind,'model':'explicit-id','project':'p','location':'global'},'key':'test-secret',
             'discover':False,'prompt':'test','max_tokens':8,'timeout':5}
    assert run(request)=='OK'
    assert factory.call_args.kwargs=={'vertexai':expected,'api_key':'test-secret'}
    assert client.models.generate_content.call_args.kwargs['config']=={'max_output_tokens':8}
    client.close.assert_called_once()
