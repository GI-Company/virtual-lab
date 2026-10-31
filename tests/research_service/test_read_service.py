import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time

import jwt
import pytest

from virtual_lab.application.engine import ResearchEngine
from virtual_lab.integrations.research_service.auth import Unauthenticated
from virtual_lab.integrations.research_service.policy import AccessPolicy, Unavailable
from virtual_lab.settings.repository import SettingsRepository, Restrictions


def update_policy(fixture, update):
    data = json.loads(fixture.policy_path.read_bytes())
    update(data)
    fixture.policy_path.write_text(json.dumps(data))


def assert_json_hash(response):
    assert response.status_code == 200, response.text
    assert response.headers['x-content-sha256'] == hashlib.sha256(response.content).hexdigest()
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def test_three_http_clients_same_authorized_report_and_exact_checks(client, fixture):
    reports = []
    for surface in ('web','chatgpt','desktop'):
        # Independently minted credentials, not an identity inferred from surface.
        headers = {'Authorization':'Bearer '+fixture.token(), 'X-VirtualLab-Surface':surface}
        projects = assert_json_hash(client.get('/v1/projects',headers=headers))['projects']
        assert [p['id'] for p in projects] == [fixture.reference['project_id']]
        experiment = assert_json_hash(client.get(fixture.experiment_url,headers=headers))
        assert experiment['reference'] == fixture.reference
        observations = assert_json_hash(client.get(fixture.experiment_url+'/observations',headers=headers))['observations']
        assert {o['epistemic_state'] for o in observations} == {'UNKNOWN','SIMULATED'}
        response = client.get(fixture.report_url,headers=headers)
        report = assert_json_hash(response)
        reports.append(response.content)
        assert report['data_origin'] == 'synthetic' and report['epistemic_state'] == 'UNKNOWN'
        assert report['summary']['peak_count'] == 128
        assert report['review_status'] == 'approved'
        assert report['workflow_check_status'] == 'PASS'
        assert {c['status'] for c in report['acceptance_checks']} == {'PASS'}
        assert 'private-fixture-operator' not in response.text
        assert 'artifact_path' not in response.text and str(fixture.root) not in response.text
    assert len(set(reports)) == 1


@pytest.mark.parametrize('case',['missing','expired','issuer','audience','signature','algorithm','unsigned','unknown-key','missing-exp','future','too-long'])
def test_invalid_identity_fails_closed(client, fixture, case):
    token = fixture.token()
    if case == 'missing':
        headers = {'Authorization':''}
    else:
        if case == 'expired': token = fixture.token(iat=int(time.time())-500,exp=int(time.time())-200)
        if case == 'issuer': token = fixture.token(iss='https://attacker.invalid')
        if case == 'audience': token = fixture.token(aud='another-resource')
        if case == 'signature': token = token[:-5]+'AAAAA'
        if case == 'future': token = fixture.token(iat=int(time.time())+100,exp=int(time.time())+300)
        if case == 'too-long': token = fixture.token(exp=int(time.time())+3600)
        if case in ('algorithm','unsigned','unknown-key','missing-exp'):
            claims = {'iss':'https://synthetic-issuer.invalid','aud':'virtuallab-synthetic-research-service',
                'sub':'synthetic-user-a','iat':int(time.time()),'exp':int(time.time())+100,'jti':'x'}
            if case == 'algorithm': token=jwt.encode(claims,'fake-secret-that-is-longer-than-thirty-two-bytes',algorithm='HS256',headers={'kid':'fixture-key'})
            if case == 'unsigned': token=jwt.encode(claims,None,algorithm='none',headers={'kid':'fixture-key'})
            if case == 'unknown-key': token=jwt.encode(claims,fixture.private_key,algorithm='RS256',headers={'kid':'unknown'})
            if case == 'missing-exp':
                del claims['exp']
                token=jwt.encode(claims,fixture.private_key,algorithm='RS256',headers={'kid':'fixture-key'})
        headers = {'Authorization':'Bearer '+token}
    response = client.get(fixture.report_url,headers=headers)
    assert response.status_code == 401
    assert response.json() == {'error':'UNAUTHENTICATED'}
    assert token not in fixture.audit_path.read_text()


def test_unrelated_account_and_forged_plan_surface_scope_are_denied(client, fixture):
    headers = {'Authorization':'Bearer '+fixture.token('synthetic-user-b',surface='web',subscription='laboratory',
        project_id=fixture.reference['project_id']), 'X-VirtualLab-Surface':'desktop'}
    for path in (fixture.experiment_url, fixture.report_url,fixture.prefix+'/changes?sequence=0'):
        assert client.get(path,headers=headers).status_code == 404
    assert client.get(fixture.report_url+'?subscription=laboratory').status_code == 404
    assert client.get(fixture.report_url.replace(fixture.reference['instance_id'],'wrong-instance')).status_code == 404
    assert client.get(fixture.report_url.replace(fixture.reference['experiment_id'],fixture.unrelated_reference['experiment_id'])).status_code == 404
    assert client.get(fixture.report_url.replace(fixture.observation['observation_id'],fixture.unrelated_observation['observation_id'])).status_code == 404


@pytest.mark.parametrize('revocation',['membership','entitlement','reports','token','all','settings','project-settings','experiment-settings'])
def test_revocation_is_effective_on_next_call(client, fixture, revocation):
    assert client.get(fixture.report_url).status_code == 200
    if revocation in ('membership','entitlement','reports','token','all'):
        def change(data):
            if revocation == 'membership': data['grants'] = data['grants'][1:]
            if revocation == 'entitlement': data['grants'][0]['research_access'] = False
            if revocation == 'reports': data['grants'][0]['reports'] = False
            if revocation == 'all': data['enabled'] = False
            if revocation == 'token': data['revoked_token_ids'] = [jwt.decode(client.headers['authorization'][7:],options={'verify_signature':False})['jti']]
        update_policy(fixture, change)
    else:
        repository = SettingsRepository(fixture.root)
        value = repository.load()
        if revocation == 'settings': value.allow_cloud = False
        if revocation == 'project-settings': value.project_rules[fixture.reference['project_id']] = Restrictions(exports=False)
        if revocation == 'experiment-settings': value.experiment_rules[fixture.reference['experiment_id']] = Restrictions(cloud=False)
        repository.save(value)
    assert client.get(fixture.report_url).status_code == 404


def test_read_only_bounded_pages_change_cursor_and_audit(client, fixture):
    def state():
        # Logical research state remains identical; audit is a separate file.
        return client.portal.call(lambda: asyncio.get_running_loop().run_in_executor(client.app.reader.pool,
            lambda: (client.app.reader.engine.ledger.get_head().model_dump(),
                     client.app.reader.engine.store._conn.total_changes)))
    before = state()
    first = assert_json_hash(client.get(fixture.prefix+'/changes?limit=1'))
    next_page = assert_json_hash(client.get(fixture.prefix+'/changes',params={'sequence':first['cursor']['sequence'],'limit':1}))
    assert next_page['cursor']['sequence'] > first['cursor']['sequence']
    assert client.get(fixture.prefix+'/changes?sequence=999999999999').status_code == 404
    assert client.get(fixture.prefix+'/changes?project_id='+fixture.unrelated_reference['project_id']).status_code == 404
    spectrum = fixture.report_url.removesuffix('report')+'spectrum'
    assert len(assert_json_hash(client.get(spectrum+'?offset=125&limit=3'))['points']) == 3
    for query in ('limit=501','limit=-1','offset=-1','limit=1&limit=2','token=bad'):
        assert client.get(spectrum+'?'+query).status_code == 404
    for method in ('POST','PUT','PATCH','DELETE'):
        assert client.request(method,fixture.experiment_url,json={'name':'No write'}).status_code == 405
    assert client.get(fixture.experiment_url+'/jobs/anything').status_code == 404
    assert state() == before
    events = [json.loads(row) for row in fixture.audit_path.read_text().splitlines()]
    assert {'ALLOWED','DENIED'} <= {e['outcome'] for e in events}
    assert any(e['actor']=='synthetic-user-a' and e['classification']=='UNKNOWN' for e in events)
    assert 'source.csv' not in fixture.audit_path.read_text()


def test_owner_thread_serializes_concurrent_reads_and_rejects_second_owner(client, fixture):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.get(fixture.report_url),range(8)))
    assert all(r.status_code == 200 for r in results)
    assert len({r.content for r in results}) == 1
    with pytest.raises(Exception):
        ResearchEngine(fixture.root)


def test_tampered_artifact_and_policy_never_return_a_report(client, fixture):
    source = fixture.root/'ms-runs'/fixture.observation['session_id']/'source.csv'
    original = source.read_bytes()
    source.write_bytes(original+b'1,2\n')
    assert client.get(fixture.report_url).status_code != 200
    source.write_bytes(original)
    fixture.policy_path.write_text('{malformed')
    assert client.get(fixture.report_url).status_code == 503


def test_audit_failure_fails_closed(client, fixture, monkeypatch):
    def fail(*args, **kwargs):
        raise Unavailable()
    monkeypatch.setattr(client.app.reader, '_audit', fail)
    for url in (fixture.report_url, fixture.report_url+'?invalid=1', '/v1/missing'):
        assert client.get(url).status_code == 503
    assert client.post(fixture.experiment_url).status_code == 503
    assert client.get(fixture.report_url,headers={'Authorization':''}).status_code == 503


def test_revocation_during_report_computation_is_rechecked(client, fixture, monkeypatch):
    from virtual_lab.integrations.research_service import reader
    original = reader.build_report
    def revoke(*args, **kwargs):
        report = original(*args, **kwargs)
        update_policy(fixture, lambda data: data['grants'][0].update(reports=False))
        return report
    monkeypatch.setattr(reader, 'build_report', revoke)
    assert client.get(fixture.report_url).status_code == 404


def test_exported_report_and_policy_schemas_match(client, fixture):
    from pathlib import Path
    from virtual_lab.integrations.research_service.contracts import SharedMSReport
    directory = Path(__file__).resolve().parents[2]/'integrations/shared-engine-contract'
    for name,model in [('service-access-policy',AccessPolicy),('service-ms-report',SharedMSReport)]:
        assert json.loads((directory/(name+'.schema.json')).read_bytes()) == model.model_json_schema()
    report = SharedMSReport.model_validate(client.get(fixture.report_url).json())
    assert report.reference.model_dump() == fixture.reference


def test_server_host_duplicate_credentials_and_extra_token_urls_are_rejected(client, fixture):
    assert client.get(fixture.report_url, headers={'Host':'attacker.invalid'}).status_code == 400
    assert client.get(fixture.report_url,headers=[('Authorization','Bearer '+fixture.token()),
        ('Authorization','Bearer '+fixture.token())]).status_code == 401
    token = jwt.encode({'sub':'synthetic-user-a'},fixture.private_key,algorithm='RS256',
                       headers={'kid':'fixture-key','jku':'https://attacker.invalid/keys'})
    assert client.get(fixture.report_url,headers={'Authorization':'Bearer '+token}).status_code == 401


def test_instance_pin_is_checked_before_opening_engine(fixture):
    from starlette.testclient import TestClient
    from virtual_lab.integrations.research_service.server import create_app
    update_policy(fixture,lambda data: data.update(instance_id='wrong-instance'))
    before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.root.glob('*.db')}
    app = create_app(root=fixture.root,policy_path=fixture.policy_path,audit_path=fixture.audit_path,
                     verifier=fixture.verifier,allowed_hosts=['testserver'])
    with pytest.raises(ValueError,match='different instance'):
        with TestClient(app):
            pass
    assert app.reader.engine is None
    assert before == {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.root.glob('*.db')}


@pytest.mark.parametrize('kind',['report','spectrum'])
def test_foreign_run_cannot_be_exposed_through_misbound_observation(client, fixture, kind):
    # Simulate an inconsistent query-store reference without changing Genesis.
    # Both the observation scope and independent completed-run scope must agree.
    async def corrupt_query_store():
        def update():
            conn = client.app.reader.engine.store._conn
            with conn:
                conn.execute('UPDATE observations SET session_id=?,artifact_sha256=? WHERE observation_id=?',
                    (fixture.unrelated_observation['session_id'],fixture.unrelated_observation['artifact_sha256'],
                     fixture.observation['observation_id']))
        await asyncio.get_running_loop().run_in_executor(client.app.reader.pool,update)
    client.portal.call(corrupt_query_store)
    url = fixture.report_url.removesuffix('report')+kind
    assert client.get(url).status_code == 404


def test_separate_categories_and_hidden_experiment_listing(client, fixture):
    update_policy(fixture,lambda data: data['grants'][0].update(spectrum=False))
    assert client.get(fixture.report_url).status_code == 200
    assert client.get(fixture.report_url.removesuffix('report')+'spectrum').status_code == 404
    repository = SettingsRepository(fixture.root)
    value = repository.load()
    value.experiment_rules[fixture.reference['experiment_id']] = Restrictions(exports=False)
    repository.save(value)
    assert client.get(fixture.prefix+'/experiments').json()['experiments'] == []
    assert all(c.get('experiment_id') != fixture.reference['experiment_id'] for c in client.get(fixture.prefix+'/changes').json()['changes'])
