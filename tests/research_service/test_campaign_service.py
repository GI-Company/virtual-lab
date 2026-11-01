"""HTTP qualification of opt-in, bounded background research using real workers."""
import asyncio
from contextlib import contextmanager
import hashlib
import json
import threading
import time
import uuid

import pytest
from starlette.testclient import TestClient

from virtual_lab.integrations.research_service.server import create_app
from virtual_lab.settings.repository import SettingsRepository, Restrictions


def update_policy(fixture, update):
    value = json.loads(fixture.policy_path.read_bytes())
    update(value)
    pending = fixture.policy_path.with_suffix('.pending')
    pending.write_text(json.dumps(value))
    pending.replace(fixture.policy_path)


def enable_campaigns(fixture):
    update_policy(fixture, lambda value: value['grants'][0].update(
        campaign_read=True, campaign_write=True, campaign_run=True))
    repository = SettingsRepository(fixture.root)
    settings = repository.load()
    settings.allow_tools = True
    repository.save(settings)


@contextmanager
def connection(fixture, *, tick_interval=.05, token=None):
    app = create_app(root=fixture.root, policy_path=fixture.policy_path,
        audit_path=fixture.audit_path, verifier=fixture.verifier,
        allowed_hosts=['testserver'], enable_campaigns=True, tick_interval=tick_interval)
    with TestClient(app, headers={'Authorization': 'Bearer '+(token or fixture.token())}) as client:
        yield client


@pytest.fixture
def campaign_client(fixture):
    enable_campaigns(fixture)
    with connection(fixture) as client:
        yield client


def command_body(**fields):
    return {'request_id': str(uuid.uuid4()), **fields}


def plan_body(**changes):
    value = {'objective': 'Compare my assumed conditions at 2 and 7 micromolar',
        'configs': [{'model_id': 'gene_expression', 'concentration_um': concentration,
                     'members': 2, 'duration_h': 1} for concentration in (2, 7)],
        'max_runs': 2, 'max_seconds': 60, 'request_id': str(uuid.uuid4())}
    value.update(changes)
    return value


def checked(response):
    assert response.status_code == 200, response.text
    assert response.headers['x-content-sha256'] == hashlib.sha256(response.content).hexdigest()
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def owner(client, callback):
    async def dispatch():
        return await asyncio.get_running_loop().run_in_executor(client.app.reader.pool, callback)
    return client.portal.call(dispatch)


def terminal_event(client, monkeypatch):
    event = threading.Event()
    engine = client.app.reader.engine
    original = engine._change

    def observe(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get('state') in ('COMPLETED', 'CANCELLED', 'NEEDS_REVIEW'):
            event.set()
        return result

    monkeypatch.setattr(engine, '_change', observe)
    return event


def create(client, fixture, **changes):
    return checked(client.post(fixture.experiment_url+'/campaigns', json=plan_body(**changes)))


def url(fixture, campaign):
    return fixture.experiment_url+'/campaigns/'+campaign['id']


def start(client, fixture, campaign):
    return checked(client.post(url(fixture, campaign)+'/start',
        json=command_body(approved_plan_sha256=campaign['plan_sha256'])))


def test_real_custom_campaign_finishes_without_http_polling(campaign_client, fixture, monkeypatch):
    client = campaign_client
    event = terminal_event(client, monkeypatch)
    campaign = create(client, fixture)
    assert campaign['state'] == 'DRAFT'
    assert [c['concentration_um'] for c in campaign['plan']['configs']] == [2, 7]
    start(client, fixture, campaign)
    # No requests or manual controller ticks drive execution during this wait.
    assert event.wait(20), 'Owner background scheduler did not finish the two real jobs'
    completed = checked(client.get(url(fixture, campaign)))
    assert completed['state'] == 'COMPLETED' and completed['next_step'] == 2
    assert len(set(completed['observations'])) == 2
    replies = []
    for surface in ('web', 'chatgpt', 'desktop'):
        reply = client.get(url(fixture, campaign)+'/results', headers={
            'Authorization': 'Bearer '+fixture.token(), 'X-VirtualLab-Surface': surface})
        results = checked(reply)
        assert results['epistemic_state'] == 'SIMULATED'
        assert len(results['results']) == 2
        assert all(r['epistemic_state'] == 'SIMULATED' for r in results['results'])
        assert all(r['numerical_check']['status'] == 'PASSED' for r in results['results'])
        assert [r['config']['concentration_um'] for r in results['results']] == [2, 7]
        assert all(r['summary'] and r['limitations'] for r in results['results'])
        assert str(fixture.root) not in reply.text and 'artifact_path' not in reply.text
        replies.append(reply.content)
    assert len(set(replies)) == 1
    listing = checked(client.get(fixture.experiment_url+'/campaigns'))
    assert [entry['id'] for entry in listing['campaigns']] == [campaign['id']]
    assert owner(client, lambda: len(client.app.reader.engine.observations(fixture.reference))) == 4


def test_create_retries_are_idempotent_and_changed_payload_conflicts(campaign_client, fixture):
    client = campaign_client
    body = plan_body()
    first = checked(client.post(fixture.experiment_url+'/campaigns', json=body))
    again = checked(client.post(fixture.experiment_url+'/campaigns', json=body))
    assert first == again
    assert client.post(fixture.experiment_url+'/campaigns',
        json={**body, 'objective': 'A different research question'}).status_code == 409
    listing = checked(client.get(fixture.experiment_url+'/campaigns'))
    assert len(listing['campaigns']) == 1
    assert client.post(url(fixture, first)+'/start',
        json=command_body(approved_plan_sha256='0'*64)).status_code == 409
    assert checked(client.get(url(fixture, first)))['state'] == 'DRAFT'


def test_cross_account_scope_and_client_claims_never_grant_access(campaign_client, fixture):
    client = campaign_client
    campaign = create(client, fixture)
    headers = {'Authorization': 'Bearer '+fixture.token('synthetic-user-b',
        project_id=fixture.reference['project_id'], subscription='laboratory', campaign_run=True),
        'X-VirtualLab-Surface': 'desktop'}
    for path in (url(fixture, campaign), url(fixture, campaign)+'/results',
                 fixture.experiment_url+'/campaigns'):
        assert client.get(path, headers=headers).status_code == 404
    assert client.post(url(fixture, campaign)+'/start', headers=headers,
        json=command_body(approved_plan_sha256=campaign['plan_sha256'])).status_code == 404
    foreign = url(fixture, campaign).replace(fixture.reference['experiment_id'],
        fixture.unrelated_reference['experiment_id'])
    assert client.get(foreign).status_code == 404
    assert client.post(foreign+'/cancel', json=command_body()).status_code == 404
    assert client.post(fixture.experiment_url+'/campaigns', headers=headers,
        json=plan_body()).status_code == 404


def test_separate_grants_and_local_settings_are_required(campaign_client, fixture):
    client = campaign_client
    campaign = create(client, fixture)
    update_policy(fixture, lambda value: value['grants'][0].update(campaign_write=False))
    assert client.post(fixture.experiment_url+'/campaigns', json=plan_body()).status_code == 404
    assert client.get(url(fixture, campaign)).status_code == 200
    update_policy(fixture, lambda value: value['grants'][0].update(campaign_write=True, campaign_run=False))
    assert client.post(url(fixture, campaign)+'/start',
        json=command_body(approved_plan_sha256=campaign['plan_sha256'])).status_code == 404
    update_policy(fixture, lambda value: value['grants'][0].update(campaign_run=True))
    repository = SettingsRepository(fixture.root)
    settings = repository.load()
    settings.experiment_rules[fixture.reference['experiment_id']] = Restrictions(tools=False)
    repository.save(settings)
    assert client.post(url(fixture, campaign)+'/start',
        json=command_body(approved_plan_sha256=campaign['plan_sha256'])).status_code == 404
    assert checked(client.get(url(fixture, campaign)))['state'] == 'DRAFT'
    update_policy(fixture, lambda value: value['grants'][0].update(campaign_read=False))
    assert client.get(url(fixture, campaign)).status_code == 404


def test_default_service_still_rejects_all_campaign_writes(client, fixture):
    enable_campaigns(fixture)
    assert client.post(fixture.experiment_url+'/campaigns', json=plan_body()).status_code == 405
    assert client.get(fixture.experiment_url+'/campaigns').status_code == 404


@pytest.mark.parametrize('body', [
    {'unexpected': True},
    {'request_id': '../../../private'},
    {'max_runs': True},
    {'configs': []},
    {'configs': [{'model_id': 'gene_expression', 'unknown_parameter': 1}]},
    {'configs': [{'model_id': 'gene_expression', 'members': True}]},
])
def test_invalid_campaign_shapes_cannot_create_work(campaign_client, fixture, body):
    client = campaign_client
    assert client.post(fixture.experiment_url+'/campaigns', json=plan_body(**body)).status_code == 400
    assert checked(client.get(fixture.experiment_url+'/campaigns'))['campaigns'] == []


@pytest.mark.parametrize('raw', [
    b'{"objective":"one","objective":"two"}',
    b'{"max_seconds":NaN}',
    b'[]',
    b'\xff',
])
def test_invalid_json_is_rejected_before_dispatch(campaign_client, fixture, raw):
    response = campaign_client.post(fixture.experiment_url+'/campaigns', content=raw,
                                   headers={'Content-Type': 'application/json'})
    assert response.status_code == 400


def test_streaming_body_byte_limit_and_unknown_query(campaign_client, fixture):
    client = campaign_client
    response = client.post(fixture.experiment_url+'/campaigns',
        content=b' '*65537, headers={'Content-Type': 'application/json'})
    assert response.status_code == 413
    # A multibyte body must be bounded by UTF-8 bytes, not character count.
    response = client.post(fixture.experiment_url+'/campaigns',
        content=json.dumps({'objective': '\u00e9'*33000}, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json'})
    assert response.status_code == 413
    assert client.post(fixture.experiment_url+'/campaigns?surface=web', json=plan_body()).status_code == 400


@pytest.mark.parametrize('revocation', ['grant', 'token', 'settings', 'malformed-policy'])
def test_background_revocation_cancels_before_additional_jobs(campaign_client, fixture, monkeypatch, revocation):
    client = campaign_client
    engine = client.app.reader.engine
    event = terminal_event(client, monkeypatch)
    campaign = create(client, fixture)
    original = engine.submit_simulation
    submitted = []

    def revoke_after_submission(*args, **kwargs):
        job = original(*args, **kwargs)
        submitted.append(job.id)
        if revocation == 'grant':
            update_policy(fixture, lambda value: value['grants'][0].update(campaign_run=False))
        elif revocation == 'token':
            import jwt
            token_id = jwt.decode(client.headers['authorization'][7:], options={'verify_signature': False})['jti']
            update_policy(fixture, lambda value: value.update(revoked_token_ids=[token_id]))
        elif revocation == 'settings':
            repository = SettingsRepository(fixture.root)
            settings = repository.load()
            settings.allow_tools = False
            repository.save(settings)
        else:
            fixture.policy_path.write_text('{broken')
        return job

    monkeypatch.setattr(engine, 'submit_simulation', revoke_after_submission)
    start(client, fixture, campaign)
    assert event.wait(20), 'Revoked campaign did not stop independently of HTTP requests'
    if revocation == 'malformed-policy':
        # Restore only the operator policy to inspect the persisted stop result.
        from virtual_lab.integrations.research_service.policy import AccessPolicy, Grant
        fixture.policy_path.write_text(AccessPolicy(instance_id=fixture.reference['instance_id'],
            enabled=True, grants=[Grant(subject='synthetic-user-a', tenant_id='synthetic-tenant-a',
                project_id=fixture.reference['project_id'], research_access=True,
                campaign_read=True)]).model_dump_json())
    done = checked(client.get(url(fixture, campaign),
        headers={'Authorization': 'Bearer '+fixture.token()}))
    assert done['state'] == 'NEEDS_REVIEW'
    assert len(submitted) == 1 and done['next_step'] == 0
    assert done['observations'] == []
    assert owner(client, lambda: len(engine._processes)) == 0


def test_restart_retains_completed_results_without_duplicate_execution(fixture, monkeypatch):
    enable_campaigns(fixture)
    with connection(fixture) as first:
        event = terminal_event(first, monkeypatch)
        campaign = create(first, fixture)
        start(first, fixture, campaign)
        assert event.wait(20)
        before = checked(first.get(url(fixture, campaign)+'/results'))
        count = owner(first, lambda: first.app.reader.engine.store._conn.execute(
            'SELECT COUNT(*) FROM application_jobs').fetchone()[0])
    with connection(fixture) as second:
        after = checked(second.get(url(fixture, campaign)+'/results'))
        assert after == before
        assert owner(second, lambda: second.app.reader.engine.store._conn.execute(
            'SELECT COUNT(*) FROM application_jobs').fetchone()[0]) == count
        assert client_token_absent(fixture)


def test_original_execution_token_expiry_stops_even_with_fresh_reader_token(fixture, monkeypatch):
    enable_campaigns(fixture)
    # The first host tick happens after this real signed execution credential
    # expires. Merely reading with a fresh token must not renew run authority.
    short_token = fixture.token(exp=int(time.time())+2)
    with connection(fixture, tick_interval=3, token=short_token) as client:
        event = terminal_event(client, monkeypatch)
        campaign = create(client, fixture)
        start(client, fixture, campaign)
        assert event.wait(8), 'Expired execution authority did not stop the saved campaign'
        done = checked(client.get(url(fixture, campaign),
            headers={'Authorization': 'Bearer '+fixture.token()}))
        assert done['state'] == 'NEEDS_REVIEW'
        assert done['next_step'] == 0 and done['observations'] == []
        assert owner(client, lambda: len(client.app.reader.engine._processes)) == 0
        assert client.post(url(fixture, campaign)+'/start',
            headers={'Authorization': 'Bearer '+fixture.token()},
            json=command_body(approved_plan_sha256=campaign['plan_sha256'])).status_code == 409


def test_paused_campaign_survives_restart_and_explicitly_resumes(fixture, monkeypatch):
    enable_campaigns(fixture)
    with connection(fixture, tick_interval=5) as client:
        campaign = create(client, fixture)
        start(client, fixture, campaign)
        paused = checked(client.post(url(fixture, campaign)+'/pause', json=command_body()))
        assert paused['state'] == 'PAUSED' and paused['next_step'] == 0
    with connection(fixture) as restarted:
        event = terminal_event(restarted, monkeypatch)
        assert checked(restarted.get(url(fixture, campaign)))['state'] == 'PAUSED'
        start(restarted, fixture, campaign)
        assert event.wait(20)
        assert checked(restarted.get(url(fixture, campaign)))['state'] == 'COMPLETED'


def test_cancelled_draft_never_submits_worker(campaign_client, fixture):
    client = campaign_client
    campaign = create(client, fixture)
    cancelled = checked(client.post(url(fixture, campaign)+'/cancel', json=command_body()))
    assert cancelled['state'] == 'CANCELLED'
    # Cancellation retry is safe and leaves the same durable outcome.
    assert checked(client.post(url(fixture, campaign)+'/cancel', json=command_body())) == cancelled
    assert checked(client.get(url(fixture, campaign)+'/results'))['results'] == []
    assert owner(client, lambda: len(client.app.reader.engine._processes)) == 0


def client_token_absent(fixture):
    audit = fixture.audit_path.read_text()
    return 'Bearer ' not in audit and 'Compare my assumed conditions' not in audit


def test_delayed_start_retry_does_not_resume_paused_campaign(fixture):
    enable_campaigns(fixture)
    with connection(fixture, tick_interval=5) as client:
        campaign = create(client, fixture)
        body = command_body(approved_plan_sha256=campaign['plan_sha256'])
        checked(client.post(url(fixture, campaign)+'/start', json=body))
        checked(client.post(url(fixture, campaign)+'/pause', json=command_body()))
        replay = checked(client.post(url(fixture, campaign)+'/start', json=body))
        assert replay['state'] == 'PAUSED' and replay['next_step'] == 0
        assert client.post(url(fixture, campaign)+'/cancel',
            json={'request_id': body['request_id']}).status_code == 409
        assert start(client, fixture, campaign)['state'] == 'RUNNING'


def test_audit_failure_stops_active_job_before_accepting_output(campaign_client, fixture, monkeypatch):
    from virtual_lab.integrations.research_service.policy import Unavailable
    client = campaign_client
    engine = client.app.reader.engine
    host = client.app.reader
    event = terminal_event(client, monkeypatch)
    campaign = create(client, fixture)
    original_submit = engine.submit_simulation
    original_audit = host._audit
    submitted = []

    def fail_audit(*args, **kwargs):
        raise Unavailable()

    def submit_then_break_audit(*args, **kwargs):
        job = original_submit(*args, **kwargs)
        submitted.append(job.id)
        monkeypatch.setattr(host, '_audit', fail_audit)
        return job

    monkeypatch.setattr(engine, 'submit_simulation', submit_then_break_audit)
    start(client, fixture, campaign)
    assert event.wait(20)
    monkeypatch.setattr(host, '_audit', original_audit)
    done = checked(client.get(url(fixture, campaign)))
    assert done['state'] == 'NEEDS_REVIEW' and done['observations'] == []
    assert len(submitted) == 1 and owner(client, lambda: not engine._processes)


def test_pagination_and_concurrent_campaigns_share_one_worker(campaign_client, fixture):
    client = campaign_client
    first, second = create(client, fixture), create(client, fixture)
    start(client, fixture, first)
    start(client, fixture, second)
    page = checked(client.get(fixture.experiment_url+'/campaigns?limit=1'))
    assert len(page['campaigns']) == 1 and page['has_more']
    assert checked(client.get(fixture.experiment_url+'/campaigns?offset=1&limit=1'))['campaigns'][0]['id'] == second['id']
    deadline = time.monotonic()+20
    while time.monotonic() < deadline:
        states = [checked(client.get(url(fixture, c)))['state'] for c in (first, second)]
        assert owner(client, lambda: len(client.app.reader.engine._processes)) <= 1
        if states == ['COMPLETED', 'COMPLETED']:
            break
        time.sleep(.05)
    else:
        pytest.fail('Shared worker did not finish both campaigns')


def test_missing_command_id_rejected(campaign_client, fixture):
    campaign = create(campaign_client, fixture)
    for action, body in [('start', {'approved_plan_sha256': campaign['plan_sha256']}),
                         ('pause', {}), ('cancel', {})]:
        assert campaign_client.post(url(fixture, campaign)+'/'+action, json=body).status_code == 400


def test_report_artifact_alteration_fails_integrity_check(campaign_client, fixture, monkeypatch):
    client = campaign_client
    event = terminal_event(client, monkeypatch)
    campaign = create(client, fixture)
    start(client, fixture, campaign)
    assert event.wait(20)
    completed = checked(client.get(url(fixture, campaign)))
    observation_id = completed['observations'][0]
    from pathlib import Path
    artifact = owner(client, lambda: next(o.artifact_path for o in
        client.app.reader.engine.store.get_observations_for_experiment(fixture.reference['experiment_id'])
        if o.observation_id == observation_id))
    Path(artifact).write_bytes(b'{"epistemic_state":"SIMULATED","tampered":true}')
    assert client.get(url(fixture, campaign)+'/results').status_code == 404


def test_interrupted_command_is_not_silently_replayed(fixture, monkeypatch):
    enable_campaigns(fixture)
    with connection(fixture, tick_interval=5) as client:
        campaign = create(client, fixture)
        body = command_body(approved_plan_sha256=campaign['plan_sha256'])
        host = client.app.reader
        original = host.campaigns.start

        def uncertain(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('Simulated lost checkpoint after start')

        monkeypatch.setattr(host.campaigns, 'start', uncertain)
        assert client.post(url(fixture, campaign)+'/start', json=body).status_code == 503
        monkeypatch.setattr(host.campaigns, 'start', original)
        assert client.post(url(fixture, campaign)+'/start', json=body).status_code == 409
        assert checked(client.get(url(fixture, campaign)))['state'] == 'RUNNING'
        checked(client.post(url(fixture, campaign)+'/pause', json=command_body()))
        assert client.post(url(fixture, campaign)+'/start', json=body).status_code == 409
        assert checked(client.get(url(fixture, campaign)))['state'] == 'PAUSED'


def test_corrupt_checkpoint_fails_host_closed_and_reaps_active_process(campaign_client, fixture, monkeypatch):
    client = campaign_client
    host, engine = client.app.reader, client.app.reader.engine
    campaign = create(client, fixture)
    original = engine.submit_simulation

    def corrupt_after_submission(*args, **kwargs):
        result = original(*args, **kwargs)
        # Corrupt a separate binding checkpoint so even the scheduler's query
        # fails. The active child must still be reaped by the outer handler.
        with engine.store._conn:
            engine.store._conn.execute('UPDATE research_campaigns SET plan=? WHERE id=?',
                ('{}', campaign['id']))
        return result

    monkeypatch.setattr(engine, 'submit_simulation', corrupt_after_submission)
    start(client, fixture, campaign)
    deadline = time.monotonic()+10
    while time.monotonic() < deadline and not owner(client, lambda: host._faulted):
        time.sleep(.05)
    assert owner(client, lambda: host._faulted and not engine._processes and not engine.settings.busy)
    assert client.post(fixture.experiment_url+'/campaigns', json=plan_body()).status_code == 503


def test_command_quota_cannot_prevent_cancellation(fixture):
    enable_campaigns(fixture)
    with connection(fixture, tick_interval=5) as client:
        campaign = create(client, fixture)
        start(client, fixture, campaign)
        def fill_history():
            conn = client.app.reader.engine.store._conn
            with conn:
                conn.executemany('INSERT INTO service_campaign_commands VALUES (?,?,?,?,?)',
                    [('synthetic-user-a', str(uuid.uuid4()), campaign['id'], '0'*64, 'APPLIED')
                     for _ in range(100)])
        owner(client, fill_history)
        assert checked(client.post(url(fixture, campaign)+'/cancel', json=command_body()))['state'] == 'CANCELLED'
