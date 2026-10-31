"""Private ASGI service. Start behind TLS/private ingress with one worker only."""
from contextlib import asynccontextmanager
import argparse
import json
from pathlib import Path
import re
import uuid

from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from virtual_lab.core.provenance_export import reject_duplicates
from virtual_lab.pilots.storage import read_bounded

from .auth import TokenVerifier, Unauthenticated
from .policy import NotFound, Unavailable
from .reader import Reader


def error(code, status):
    headers = {'WWW-Authenticate':'Bearer'} if status == 401 else {}
    return JSONResponse({'error':code}, status_code=status, headers=headers)


class Boundary:
    def __init__(self, app, verifier, reader):
        self.app, self.verifier, self.reader = app, verifier, reader

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        request_id = str(uuid.uuid4())
        principal = None
        surface = 'unspecified'

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = [*message.get('headers', []),
                    (b'cache-control', b'no-store'), (b'pragma', b'no-cache'),
                    (b'x-content-type-options', b'nosniff'),
                    (b'x-request-id', request_id.encode())]
            await send(message)

        try:
            headers = scope['headers']
            labels = [v for k,v in headers if k == b'x-virtuallab-surface']
            if len(labels) == 1 and labels[0] in (b'web',b'chatgpt',b'desktop'):
                surface = labels[0].decode()
            values = [v for k,v in headers if k == b'authorization']
            if len(values) != 1 or not values[0].startswith(b'Bearer '):
                raise Unauthenticated()
            principal = self.verifier.verify(values[0][7:].decode('ascii'))
            if (scope['method'] != 'GET' or len(scope['path']) > 2048 or
                len(scope['query_string']) > 2048 or any(k == b'transfer-encoding' or
                (k == b'content-length' and v != b'0') for k,v in headers)):
                await self.reader.reject(principal, request_id, surface)
                response = error('READ_ONLY_REQUEST_REQUIRED', 405 if scope['method'] != 'GET' else 400)
                await response(scope, receive, secure_send)
                return
            scope.setdefault('state', {}).update(principal=principal, request_id=request_id, surface=surface)
            await self.app(scope, receive, secure_send)
        except (Unauthenticated, UnicodeError):
            try:
                await self.reader.reject(None, request_id, surface)
                response = error('UNAUTHENTICATED', 401)
            except Unavailable:
                response = error('SERVICE_UNAVAILABLE', 503)
            await response(scope, receive, secure_send)
        except Unavailable:
            await error('SERVICE_UNAVAILABLE', 503)(scope, receive, secure_send)


def create_app(*, root, policy_path, audit_path, verifier, allowed_hosts):
    if not allowed_hosts or any('*' in host for host in allowed_hosts):
        raise ValueError('Explicit allowed hosts are required; wildcards are not allowed')
    reader = Reader(root, policy_path, audit_path)

    @asynccontextmanager
    async def lifespan(app):
        await reader.start()
        try:
            yield
        finally:
            await reader.close()

    async def read(request: Request):
        try:
            params = request.path_params
            if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value) for value in params.values()):
                raise NotFound()
            scope = dict(params)
            operation = request.scope['route_operation']
            allowed = {'offset','limit'} if operation in ('experiments.list','observations.list','spectrum.get') else {'sequence','limit'} if operation == 'changes.list' else set()
            if set(request.query_params) - allowed or any(len(request.query_params.getlist(k)) != 1 for k in request.query_params):
                raise ValueError()
            query = {}
            for key in allowed:
                value = request.query_params.get(key, '100' if key == 'limit' else '0')
                if not re.fullmatch('[0-9]{1,16}', value):
                    raise ValueError()
                query[key] = int(value)
                maximum = 500 if operation == 'spectrum.get' else 100
                if key == 'limit' and not 1 <= query[key] <= maximum:
                    raise ValueError()
            raw, digest = await reader.read(request.state.principal, operation, scope, query,
                request.state.request_id, request.state.surface)
            return Response(raw, media_type='application/json', headers={'X-Content-SHA256':digest})
        except (ValueError, NotFound):
            await reader.reject(request.state.principal, request.state.request_id, request.state.surface)
            return error('NOT_FOUND', 404)
        except Unavailable:
            return error('SERVICE_UNAVAILABLE', 503)

    prefix = '/v1/instances/{instance_id}/projects/{project_id}'
    experiment = prefix+'/experiments/{experiment_id}'
    observation = experiment+'/observations/{observation_id}'
    specs = [('/v1/projects','projects.list'), (prefix+'/experiments','experiments.list'),
        (experiment,'experiment.get'), (experiment+'/observations','observations.list'),
        (observation+'/report','report.get'), (observation+'/spectrum','spectrum.get'),
        (prefix+'/changes','changes.list')]
    routes = []
    for path, operation in specs:
        # A distinct endpoint binds the allowlisted operation; never a query field.
        async def endpoint(request, _operation=operation):
            request.scope['route_operation'] = _operation
            return await read(request)
        routes.append(Route(path, endpoint, methods=['GET']))

    async def missing(request, exc):
        try:
            await reader.reject(request.state.principal, request.state.request_id, request.state.surface)
        except Unavailable:
            return error('SERVICE_UNAVAILABLE', 503)
        return error('NOT_FOUND', 404)

    async def unavailable(request, exc):
        return error('SERVICE_UNAVAILABLE', 503)

    app = Starlette(routes=routes, lifespan=lifespan,
                    exception_handlers={404:missing, Unavailable:unavailable}, debug=False)
    return Boundary(TrustedHostMiddleware(app, allowed_hosts=list(allowed_hosts), www_redirect=False), verifier, reader)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path, help='Explicit existing hosted instance; never a desktop default')
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--identity', required=True, type=Path, help='JSON: issuer, audience, public_keys (kid to PEM)')
    parser.add_argument('--audit', required=True, type=Path)
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    identity = json.loads(read_bounded(args.identity, 65536), object_pairs_hook=reject_duplicates)
    if set(identity) != {'issuer','audience','public_keys'}:
        parser.error('Identity config requires issuer, audience and public_keys only')
    app = create_app(root=args.root, policy_path=args.policy, audit_path=args.audit,
        verifier=TokenVerifier(**identity), allowed_hosts=['127.0.0.1','localhost'])
    import uvicorn
    # No public bind flag, reload, extra workers, proxy trust or access-token logging.
    # A reviewed TLS proxy may reach this loopback listener on the same host.
    uvicorn.run(app, host='127.0.0.1', port=args.port, workers=1, proxy_headers=False,
                access_log=False, limit_concurrency=16, timeout_keep_alive=5,
                h11_max_incomplete_event_size=16384)


if __name__ == '__main__':
    main()
