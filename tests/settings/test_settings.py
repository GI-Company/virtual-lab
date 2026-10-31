"""Policy and process integration, using only a loopback fixture server."""
import json
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from virtual_lab.settings import SettingsRepository, SettingsService, Settings, Provider
from virtual_lab.settings.service import route_for

@pytest.fixture
def repo(tmp_path):
    return SettingsRepository(tmp_path)

def enable(repo, **overrides):
    value=repo.load().model_dump()
    value.update(assistant_enabled=True,**overrides)
    return repo.save(value)

def test_private_restart_migration_and_reject_unknown_schema(repo):
    assert not repo.load().assistant_enabled
    value=enable(repo, predictions_enabled=True, learning_enabled=False)
    assert SettingsRepository(repo.root).load()==value
    assert repo.path.stat().st_mode & 0o777 == 0o600
    repo.path.write_text('{"version":0,"predictions_enabled":true}')
    assert repo.load().version==1 and repo.load().predictions_enabled
    assert not repo.load().assistant_enabled
    for raw in ('{"version":9}', '{"version":1,"api_key":"secret"}', '{"allow_cloud":false,"allow_cloud":true}'):
        repo.path.write_text(raw)
        with pytest.raises(ValueError): repo.load()

@pytest.mark.parametrize('url,route',[
    ('http://127.0.0.1:1234/v1','loopback'),('http://[::1]:1234/v1','loopback'),
    ('http://localhost:1234/v1','loopback'),('http://192.168.1.5/v1','lan'),
    ('https://server.example/v1','cloud'),('https://8.8.8.8/v1','cloud')])
def test_route_classification(url,route):
    assert route_for(Provider(endpoint=url))==route

@pytest.mark.parametrize('url',['file:///tmp/key','http://user:pass@localhost/v1','http://0.0.0.0/v1','http://169.254.169.254/v1','http://localhost/v1?key=secret'])
def test_invalid_routes(url):
    with pytest.raises(ValueError): route_for(Provider(endpoint=url))

def test_hierarchy_and_independent_switches(repo,tmp_path):
    admin=tmp_path/'admin.json'; admin.write_text('{"cloud":false}')
    repo.admin_path=admin
    enable(repo, predictions_enabled=True, learning_enabled=False, allow_cloud=True,
           project_rules={'p':{'assistant':False}},experiment_rules={'e':{'exports':False}})
    repo.require('predictions','p','e')
    with pytest.raises(PermissionError): repo.require('learning')
    with pytest.raises(PermissionError): repo.require('assistant','p')
    with pytest.raises(PermissionError): repo.require('exports','other','e')
    with pytest.raises(PermissionError): repo.require('assistant',route='cloud')
    assert repo.require('assistant','other',route='loopback')
    admin.write_text('not json')
    with pytest.raises(ValueError): repo.require('assistant')

@pytest.fixture
def server():
    calls=[]; started=threading.Event(); unblock=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            calls.append(self.path)
            self.send_response(200); self.end_headers()
            self.wfile.write(b'{"data":[{"id":"fixture-model"}]}')
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(data); started.set()
            if data['messages'][0]['content']=='wait': unblock.wait(5)
            if data['messages'][0]['content']=='redirect':
                self.send_response(302); self.send_header('Location','https://example.com'); self.end_headers(); return
            self.send_response(200); self.end_headers()
            try: self.wfile.write(b'{"choices":[{"message":{"content":"fixture answer"}}]}')
            except (BrokenPipeError,ConnectionResetError): pass
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=srv.serve_forever,daemon=True); thread.start()
    yield f'http://127.0.0.1:{srv.server_port}/v1',calls,started,unblock
    unblock.set(); srv.shutdown(); srv.server_close(); thread.join(2)

def configure(repo,server):
    s=enable(repo).model_dump()
    s['provider'].update(model='fixture-model',endpoint=server[0])
    repo.save(s)
    service=SettingsService(repo)
    from types import SimpleNamespace
    service.credentials=SimpleNamespace(get_api_key=lambda _:None)
    return service

def test_actual_server_discovery_generation_and_no_redirect(repo,server,monkeypatch):
    service=configure(repo,server)
    monkeypatch.setenv('HTTPS_PROXY','http://bad.invalid')
    assert service.request('',discover=True)==['fixture-model']
    assert service.request('hello')=='fixture answer'
    assert server[1][1]['model']=='fixture-model'
    with pytest.raises(RuntimeError,match='failed'): service.request('redirect')
    assert len(server[1])==3 and not service.busy and service._process is None

def test_disabled_routes_rejected_before_any_request(repo,server):
    service=configure(repo,server)
    s=repo.load().model_dump(); s['allow_loopback']=False; repo.save(s)
    with pytest.raises(PermissionError): service.request('hello')
    assert not server[1]
    s['allow_loopback']=True; s['provider']['kind']='gemini'; repo.save(s)
    with pytest.raises(PermissionError): service.request('hello')
    assert not server[1]

def start_request(service):
    failures=[]
    def run():
        try: service.request('wait')
        except Exception as exc: failures.append(exc)
    thread=threading.Thread(target=run); thread.start()
    return thread, failures

def test_cancel_unload_and_shared_training_slot(repo,server):
    service=configure(repo,server)
    thread,failures=start_request(service)
    assert server[2].wait(5)
    with pytest.raises(RuntimeError): service.save(repo.load())
    with pytest.raises(RuntimeError): service.reserve('training')
    service.unload(); thread.join(5)
    assert not thread.is_alive() and failures and not service.busy
    assert service._process is None
    service.reserve('training')
    with pytest.raises(RuntimeError): service.request('hello')
    service.release('training')
    assert not service.busy

@pytest.mark.parametrize('revocation',['assistant_enabled','allow_loopback','scope'])
def test_revocation_discards_inflight_result(repo,server,revocation):
    service=configure(repo,server); service.context=lambda:('p','e')
    thread,failures=start_request(service)
    assert server[2].wait(5)
    value=repo.load().model_dump()
    if revocation=='scope': value['experiment_rules']={'e':{'assistant':False}}
    else: value[revocation]=False
    repo.save(value)
    thread.join(5)
    assert not thread.is_alive() and failures and not service.busy

def test_model_registry_and_disk_gate(repo,tmp_path,monkeypatch):
    model=tmp_path/'models'/'fixture'; model.mkdir(parents=True); (model/'config.json').write_text('{}')
    enable(repo, model_directory=str(model.parent),provider={'kind':'mlx','model':'fixture','model_path':str(model)})
    service=SettingsService(repo)
    assert service.registry()[0]['path']==str(model)
    monkeypatch.setattr(service,'resource_status',lambda:{'free_gib':0})
    with pytest.raises(RuntimeError,match='disk'): service.request('hello')
    assert not service.busy


def test_plaintext_credential_backend_rejected(monkeypatch):
    from virtual_lab.settings.credentials import OSCredentials
    import keyring
    from types import SimpleNamespace
    monkeypatch.setattr(keyring,'get_keyring',lambda:SimpleNamespace())
    credentials=OSCredentials()
    assert credentials.get_api_key('gemini') is None
    with pytest.raises(RuntimeError,match='plaintext'):
        credentials.set_api_key('gemini','fixture-secret')


def test_settings_urls_cannot_store_credentials(repo):
    s=repo.load().model_dump()
    s['provider']['endpoint']='http://localhost/v1?api_key=secret'
    with pytest.raises(ValueError): repo.save(s)
    assert not repo.path.exists()


def test_managed_tool_policy_checks_before_executor(repo):
    from unittest.mock import Mock
    from virtual_lab.ai.agent.policy import PolicyEngine
    service=SettingsService(repo)
    enable(repo)
    registry=Mock(); recorder=Mock()
    policy=PolicyEngine(registry,recorder,settings=service)
    with pytest.raises(PermissionError): policy.execute_tool('episode','read',{})
    registry.get_tool.assert_not_called()
    with pytest.raises(PermissionError): policy.execute_approved_action('episode','proposal','act',{})


def test_compatible_credentials_are_scoped_to_endpoint():
    from virtual_lab.settings.service import credential_account
    first=Provider(endpoint='http://127.0.0.1:1234/v1')
    other=Provider(endpoint='http://127.0.0.1:4321/v1')
    assert credential_account(first)!=credential_account(other)
    assert credential_account(first)==credential_account(Provider(endpoint=first.endpoint+'/'))
    assert credential_account(Provider(kind='gemini'))=='gemini'


def test_result_from_changed_project_is_discarded(repo,server):
    service=configure(repo,server)
    context=['first','exp-one']
    service.context=lambda:tuple(context)
    thread,failures=start_request(service)
    assert server[2].wait(5)
    context[:]=['second','exp-two']
    server[3].set(); thread.join(5)
    assert not thread.is_alive() and failures
    assert 'context changed' in str(failures[0])
    assert not service.busy
