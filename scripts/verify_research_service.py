"""Verify a separate loopback HTTP process with synthetic data and ephemeral tokens."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx

from scripts.research_service_fixture import seed_synthetic_fixture


def fingerprints(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def verify(directory):
    fixture = seed_synthetic_fixture(directory/'fixture')
    before = fingerprints(fixture.root)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        port = listener.getsockname()[1]
    cmd = [sys.executable,'-m','virtual_lab.integrations.research_service.server',
        '--root',str(fixture.root),'--policy',str(fixture.policy_path),
        '--identity',str(fixture.identity_path),'--audit',str(fixture.audit_path),'--port',str(port)]
    checks = {}
    log = directory/'http-server.log'
    with log.open('wb') as stream:
        process = subprocess.Popen(cmd,stdout=stream,stderr=stream)
        try:
            base = f'http://127.0.0.1:{port}'
            deadline = time.monotonic()+20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Service failed to start; inspect http-server.log')
                try:
                    if httpx.get(base+'/v1/projects',timeout=.5,trust_env=False).status_code == 401:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError('Service readiness deadline exceeded')
            reports, clients = [], []
            try:
                for surface in ('web','chatgpt','desktop'):
                    client = httpx.Client(base_url=base,headers={'Authorization':'Bearer '+fixture.token(),
                        'X-VirtualLab-Surface':surface},timeout=10,trust_env=False)
                    clients.append(client)
                    projects = client.get('/v1/projects')
                    assert projects.status_code == 200
                    assert [p['id'] for p in projects.json()['projects']] == [fixture.reference['project_id']]
                    assert client.get(fixture.experiment_url).json()['reference'] == fixture.reference
                    response = client.get(fixture.report_url)
                    assert response.status_code == 200
                    assert response.headers['x-content-sha256'] == hashlib.sha256(response.content).hexdigest()
                    report = response.json()
                    assert report['data_origin'] == 'synthetic' and report['epistemic_state'] == 'UNKNOWN'
                    assert report['workflow_check_status'] == 'PASS'
                    reports.append(response.content)
                    cursor = client.get(fixture.prefix+'/changes').json()['cursor']
                    assert client.get(fixture.prefix+'/changes',params={'sequence':cursor['sequence']}).json()['changes'] == []
                assert len(set(reports)) == 1
                checks.update(independent_http_clients=True,same_report_sha256=True,reconnect_cursor=True)
                (directory/'verified-report.json').write_bytes(reports[0])
                with httpx.Client(base_url=base,headers={'Authorization':'Bearer '+fixture.token('synthetic-user-b',
                        subscription='laboratory',surface='desktop')},trust_env=False) as unrelated:
                    assert unrelated.get(fixture.report_url).status_code == 404
                    assert unrelated.get(fixture.experiment_url).status_code == 404
                    assert unrelated.get(fixture.prefix+'/changes?sequence=0').status_code == 404
                checks['cross_tenant_denial'] = True
                with httpx.Client(base_url=base,trust_env=False) as anonymous:
                    assert anonymous.get(fixture.report_url).status_code == 401
                assert clients[0].post(fixture.experiment_url,json={'name':'forbidden'}).status_code == 405
                checks.update(anonymous_denial=True,mutations_denied=True)
                policy = json.loads(fixture.policy_path.read_bytes())
                policy['grants'] = policy['grants'][1:]
                fixture.policy_path.write_text(json.dumps(policy))
                assert all(c.get(fixture.report_url).status_code == 404 for c in clients)
                checks['revoked_on_all_clients'] = True
            finally:
                for client in clients:
                    client.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    after = fingerprints(fixture.root)
    assert before == after, 'Read-only HTTP session changed research state'
    checks['research_files_unchanged'] = True
    audit = [json.loads(line) for line in fixture.audit_path.read_text().splitlines()]
    assert {'ALLOWED','DENIED'} <= {e['outcome'] for e in audit}
    checks['structured_audit'] = True
    return {'format':'virtuallab-read-service-qualification-v1','checks':checks,
        'passed':all(checks.values()),'data_origin':'synthetic','peak_count':128,
        'report_sha256':hashlib.sha256(reports[0]).hexdigest(),
        'reference':fixture.reference,'research_file_sha256':after,
        'versions':{name:importlib.metadata.version(name) for name in ('starlette','uvicorn','PyJWT','cryptography','httpx')},
        'limits':['Loopback HTTP qualification, not public HTTPS or deployment.',
                  'Three independent HTTP clients, not live website, ChatGPT OAuth or paired native UI.',
                  'Ephemeral synthetic token issuer, not production accounts or subscription integration.',
                  'Workflow and byte integrity only; no scientific validation.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New qualification directory')
    args = parser.parse_args()
    args.output.mkdir(parents=True,mode=0o700,exist_ok=False)
    result = verify(args.output)
    (args.output/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'checks':result['checks'],'evidence':str(args.output/'validation.json')}))


if __name__ == '__main__':
    main()
