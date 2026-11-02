"""Exercise bounded custom research against a separate real HTTP service process."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import httpx

from scripts.research_service_fixture import seed_synthetic_fixture
from scripts.service_process import launch_service, stop_service
from virtual_lab.settings.repository import SettingsRepository


def checked(response):
    assert response.status_code == 200, f'Unexpected HTTP status: {response.status_code}'
    assert response.headers['x-content-sha256'] == hashlib.sha256(response.content).hexdigest()
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def update_policy(fixture, change):
    value = json.loads(fixture.policy_path.read_bytes())
    change(value)
    pending = fixture.policy_path.with_suffix('.pending')
    pending.write_text(json.dumps(value))
    pending.replace(fixture.policy_path)


@contextmanager
def server(fixture, directory):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    cmd = [sys.executable, '-m', 'virtual_lab.integrations.research_service.server',
           '--root', str(fixture.root), '--policy', str(fixture.policy_path),
           '--identity', str(fixture.identity_path), '--audit', str(fixture.audit_path),
           '--port', str(port), '--enable-campaigns']
    with (directory/'http-server.log').open('ab') as stream:
        process = launch_service(cmd, stream)
        try:
            base = f'http://127.0.0.1:{port}'
            deadline = time.monotonic()+20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Service failed to start; inspect http-server.log')
                try:
                    if httpx.get(base+'/v1/projects', timeout=.5, trust_env=False).status_code == 401:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError('Service readiness deadline exceeded')
            yield base
        finally:
            stop_service(process)


def client(base, fixture, subject='synthetic-user-a', surface='web'):
    return httpx.Client(base_url=base, timeout=10, trust_env=False, follow_redirects=False,
        headers={'Authorization': 'Bearer '+fixture.token(subject), 'X-VirtualLab-Surface': surface})


def command(**fields):
    return {'request_id': str(uuid.uuid4()), **fields}


def wait_for_audit(fixture, campaign_id, predicate):
    deadline = time.monotonic()+20
    while time.monotonic() < deadline:
        events = []
        for row in fixture.audit_path.read_text().splitlines():
            try:
                event = json.loads(row)
            except ValueError:
                continue  # A writer may be appending the last line.
            if event['scope'].get('campaign_id') == campaign_id:
                events.append(event)
        if predicate(events):
            return
        time.sleep(.1)
    raise AssertionError('Background execution did not produce the required audit outcome')


def verify(directory):
    fixture = seed_synthetic_fixture(directory/'fixture')
    update_policy(fixture, lambda value: value['grants'][0].update(
        campaign_read=True, campaign_write=True, campaign_run=True))
    repository = SettingsRepository(fixture.root)
    settings = repository.load()
    settings.allow_tools = True
    repository.save(settings)
    path = fixture.experiment_url+'/campaigns'
    body = command(objective='Compare two user-defined gene-expression assumptions',
        configs=[{'model_id': 'gene_expression', 'compound': 'Research hypothesis',
                  'members': 3, 'duration_h': 1, 'concentration_um': value} for value in (2.5, 8.25)],
        max_runs=2, max_seconds=60)
    checks = {}
    with server(fixture, directory) as base:
        with client(base, fixture) as web:
            campaign = checked(web.post(path, json=body))
            assert checked(web.post(path, json=body))['id'] == campaign['id']
            assert web.post(path, json={**body, 'objective': 'Changed inputs'}).status_code == 409
            checks['idempotent_create_and_conflict'] = True
            item = path+'/'+campaign['id']
            checked(web.post(item+'/start', json=command(approved_plan_sha256=campaign['plan_sha256'])))
        # The initiating HTTP client is closed. No HTTP requests or SQLite
        # readers drive execution here; inspect only the operator's audit file.
        wait_for_audit(fixture, campaign['id'], lambda events: len([e for e in events
            if e['operation'] == 'campaign.advance' and e['outcome'] == 'ALLOWED']) >= 4)
        replies = []
        for surface in ('web', 'chatgpt', 'desktop'):
            with client(base, fixture, surface=surface) as reader:
                done = checked(reader.get(item))
                assert done['state'] == 'COMPLETED' and done['next_step'] == 2
                response = reader.get(item+'/results')
                report = checked(response)
                assert report['epistemic_state'] == 'SIMULATED'
                assert [r['config']['concentration_um'] for r in report['results']] == [2.5, 8.25]
                assert all(r['numerical_check']['status'] == 'PASSED' for r in report['results'])
                replies.append(response.content)
        assert len(set(replies)) == 1
        checks.update(background_progress_after_disconnect=True, custom_conditions_executed=True,
                      three_independent_client_hashes_match=True, simulated_classification=True)
        (directory/'campaign-results.json').write_bytes(replies[0])
        digest = hashlib.sha256(replies[0]).hexdigest()
        (directory/'campaign-results.json.sha256').write_text(digest+'  campaign-results.json\n')
        altered = json.loads(replies[0])
        altered['results'][0]['summary'][0]['treated']['median'] = 999999
        assert hashlib.sha256(json.dumps(altered).encode()).hexdigest() != digest
        checks['altered_report_bytes_fail_recorded_digest'] = True
        with client(base, fixture, subject='synthetic-user-b') as unrelated:
            assert unrelated.get(item+'/results').status_code == 404
            assert unrelated.post(item+'/start', json=command(
                approved_plan_sha256=campaign['plan_sha256'])).status_code == 404
        checks['unrelated_account_denied'] = True
        with client(base, fixture) as web:
            assert web.post(path, content=b' '*65537,
                            headers={'Content-Type': 'application/json'}).status_code == 413
        checks['http_body_limit'] = True
    # Complete shutdown/reopen preserves the exact report, with no re-execution.
    with server(fixture, directory) as base:
        with client(base, fixture) as reader:
            response = reader.get(item+'/results')
            checked(response)
            assert response.content == replies[0]
            checks['completed_report_survives_process_restart'] = True
            next_campaign = checked(reader.post(path, json={**body, 'request_id': str(uuid.uuid4())}))
            next_item = path+'/'+next_campaign['id']
            checked(reader.post(next_item+'/start', json=command(
                approved_plan_sha256=next_campaign['plan_sha256'])))
            update_policy(fixture, lambda value: value['grants'][0].update(campaign_run=False))
        wait_for_audit(fixture, next_campaign['id'], lambda events: any(
            e['operation'] == 'campaign.stopped' for e in events))
        with client(base, fixture) as reader:
            stopped = checked(reader.get(next_item))
            assert stopped['state'] == 'NEEDS_REVIEW' and stopped['next_step'] < 2
        checks['run_revocation_stops_background_work'] = True
        update_policy(fixture, lambda value: value['grants'][0].update(research_access=False))
        for surface in ('web', 'chatgpt', 'desktop'):
            with client(base, fixture, surface=surface) as reader:
                assert reader.get(item+'/results').status_code == 404
        checks['project_revocation_denies_all_clients'] = True
    audit = fixture.audit_path.read_text()
    assert 'Bearer ' not in audit and body['objective'] not in audit
    checks['audit_excludes_credentials_and_research_inputs'] = True
    return {'format': 'virtuallab-campaign-service-qualification-v1',
        'verified_at': datetime.now(timezone.utc).isoformat(), 'passed': all(checks.values()),
        'checks': checks, 'report_sha256': digest, 'campaign_id': campaign['id'],
        'reference': fixture.reference, 'data_origin': 'synthetic',
        'limits': ['Local HTTP with ephemeral synthetic identity; no production account integration.',
            'Independent HTTP clients are not the actual website, ChatGPT or desktop interfaces.',
            'Only finite, acknowledged registered CPU simulations; no adaptive AI planner or wet-lab control.',
            'Execution authority expires with the original service token (at most 15 minutes).',
            'Checksums attest bytes, not a publisher signature or biological validity.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New isolated evidence directory')
    args = parser.parse_args()
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    result = verify(args.output)
    (args.output/'validation.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'passed': result['passed'], 'checks': result['checks'],
                      'evidence': str(args.output/'validation.json')}))


if __name__ == '__main__':
    main()
