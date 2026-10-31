"""Allowlisted projections executed solely on the ResearchEngine owner thread."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import stat
import time
import uuid

from virtual_lab.application.contracts import ExperimentRef, ChangeCursor
from virtual_lab.application.engine import ResearchEngine
from virtual_lab.pilots.ms_workflow import json_bytes
from virtual_lab.pilots.reporting import build_report
from virtual_lab.pilots.storage import checked_path, read_bounded

from .policy import NotFound, Unavailable, PolicyRepository
from .contracts import SharedMSReport


def select(value, *keys):
    return {key: value[key] for key in keys}


class Reader:
    """Owns the sole engine; HTTP never receives its SQLite connections or paths.

    The public API is read-only. Normal engine startup recovery and the separate
    service audit file may write; accepted HTTP reads never append research events.
    """
    def __init__(self, root, policy_path, audit_path):
        self.root = checked_path(root)
        self.policy = PolicyRepository(policy_path)
        self.audit_path = checked_path(audit_path)
        if self.audit_path == self.policy.path or self.audit_path.is_relative_to(self.root):
            raise ValueError('Keep the service audit separate from research state and policy')
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='research-owner')
        self.pending = 0
        self.engine = None

    async def start(self):
        try:
            await asyncio.get_running_loop().run_in_executor(self.pool, self._open)
        except BaseException:
            self.pool.shutdown(wait=True)
            raise

    def _open(self):
        policy = self.policy.load()
        if not policy.enabled or not (self.root/'instance.json').is_file():
            raise ValueError('Select an existing instance and explicitly enable service access')
        if json.loads(read_bounded(self.root/'instance.json', 1024)).get('id') != policy.instance_id:
            raise ValueError('Policy is pinned to a different instance')
        self.engine = ResearchEngine(self.root)
        try:
            if self.engine.instance_id != policy.instance_id:
                raise ValueError('Policy is pinned to a different instance')
            self.audit_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._audit(None, 'service.start', {}, 'READY', str(uuid.uuid4()), 'service')
        except BaseException:
            self.engine.close()
            self.engine = None
            raise

    async def close(self):
        try:
            if self.engine is not None:
                await asyncio.get_running_loop().run_in_executor(self.pool, self.engine.close)
        finally:
            self.pool.shutdown(wait=True)

    async def read(self, principal, operation, scope, query, request_id, surface='unspecified'):
        if self.pending >= 8:
            raise Unavailable()
        self.pending += 1
        future = asyncio.get_running_loop().run_in_executor(self.pool, self._read,
            principal, operation, scope, query, request_id, surface)
        # Timed-out work retains its queue slot until it really completes.
        future.add_done_callback(lambda _: setattr(self, 'pending', self.pending - 1))
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=15)
        except asyncio.TimeoutError as exc:
            raise Unavailable() from exc

    def _audit(self, principal, operation, scope, outcome, request_id, surface, classification=None):
        event = {'format':'virtuallab-service-audit-v1', 'time':int(time.time()),
            'request_id':request_id, 'actor':principal.subject if principal else None,
            'surface_diagnostic':surface, 'operation':operation, 'scope':scope,
            'outcome':outcome, 'classification':classification}
        try:
            fd = os.open(checked_path(self.audit_path), os.O_WRONLY | os.O_APPEND | os.O_CREAT |
                         getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0), 0o600)
            with os.fdopen(fd, 'ab') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError('Audit must be a private regular file')
                if os.name != 'nt':
                    os.fchmod(stream.fileno(), 0o600)
                stream.write((json.dumps(event, sort_keys=True, separators=(',',':'), allow_nan=False)+'\n').encode())
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, ValueError) as exc:
            raise Unavailable() from exc

    async def reject(self, principal, request_id, surface):
        try:
            await self.read(principal, 'request.reject', {}, {}, request_id, surface)
        except NotFound:
            pass

    def _grant(self, principal, scope, category):
        engine = self.engine
        grant = self.policy.load().authorize(principal, engine.instance_id, scope['project_id'], category)
        if scope.get('instance_id') != engine.instance_id:
            raise NotFound()
        try:
            engine.settings.repository.require('exports', scope['project_id'], scope.get('experiment_id'), route='cloud')
        except PermissionError as exc:
            raise NotFound() from exc
        return grant

    def _read(self, principal, operation, scope, query, request_id, surface):
        classification = None
        try:
            self.engine._check()
            if operation == 'projects.list':
                result = []
                for project in self.engine.projects():
                    item_scope = {'instance_id':self.engine.instance_id, 'project_id':project['id']}
                    try:
                        grant = self._grant(principal, item_scope, 'metadata')
                    except NotFound:
                        continue
                    result.append({**select(project, 'id','name','domain_id','created_at'),
                                   'instance_id':self.engine.instance_id, 'tenant_id':grant.tenant_id})
                # Re-resolve all grants before returning this request's projection.
                for item in result:
                    self._grant(principal, {'instance_id':item['instance_id'],'project_id':item['id']}, 'metadata')
                data = {'format':'virtuallab-service-projects-v1','projects':result}
            else:
                category = {'experiments.list':'metadata','experiment.get':'metadata',
                    'observations.list':'metadata','report.get':'reports',
                    'spectrum.get':'spectrum','changes.list':'changes'}[operation]
                grant = self._grant(principal, scope, category)
                data = self._project_read(operation, scope, query)
                if self._grant(principal, scope, category) != grant:
                    raise NotFound()
                classification = data.get('epistemic_state')
            raw = json_bytes(data)
            if len(raw) > 1024*1024:
                raise Unavailable()
            self._audit(principal, operation, scope, 'ALLOWED', request_id, surface, classification)
            return raw, hashlib.sha256(raw).hexdigest()
        except (NotFound, ValueError, KeyError) as exc:
            self._audit(principal, operation, scope, 'DENIED', request_id, surface)
            raise NotFound() from exc
        except Exception as exc:
            # Do not include filesystem paths, spectra, tokens or exception text in responses/logs.
            self._audit(principal, operation, scope, 'UNAVAILABLE', request_id, surface)
            raise Unavailable() from exc

    def _reference(self, scope):
        ref = ExperimentRef(**select(scope, 'instance_id','project_id','experiment_id'))
        self.engine.experiment(ref)
        return ref

    def _experiment_projection(self, row):
        return select(row, 'id','project_id','label','research_question','status','created_at')

    def _visible_experiment(self, project_id, experiment_id):
        try:
            self.engine.settings.repository.require('exports', project_id, experiment_id, route='cloud')
            return True
        except PermissionError:
            return False

    def _project_read(self, operation, scope, query):
        engine = self.engine
        engine._project(scope['project_id'])
        if operation == 'experiments.list':
            rows = [r for r in engine.experiments(scope['project_id'])
                    if self._visible_experiment(scope['project_id'], r['id'])]
            offset, limit = query['offset'], query['limit']
            return {'experiments':[self._experiment_projection(r) for r in rows[offset:offset+limit]],
                    'offset':offset,'has_more':offset+limit < len(rows)}
        if operation == 'changes.list':
            cursor = ChangeCursor(instance_id=scope['instance_id'],project_id=scope['project_id'],sequence=query['sequence'])
            page = engine.changes(scope['project_id'], cursor, limit=query['limit'])
            fields = ('sequence','timestamp_utc','operation','project_id','experiment_id',
                      'observation_id','job_id','run_id')
            page['changes'] = [{k:v for k,v in c.items() if k in fields} for c in page['changes']
                if not c.get('experiment_id') or self._visible_experiment(scope['project_id'], c['experiment_id'])]
            return page
        ref = self._reference(scope)
        if operation == 'experiment.get':
            return {'reference':ref.model_dump(), 'experiment':self._experiment_projection(engine.experiment(ref))}
        if operation == 'observations.list':
            rows = engine.observations(ref)
            offset, limit = query['offset'], query['limit']
            return {'reference':ref.model_dump(), 'observations':[select(r, 'observation_id','experiment_id',
                    'kind','epistemic_state','artifact_sha256','session_id') for r in rows[offset:offset+limit]],
                    'offset':offset,'has_more':offset+limit < len(rows)}
        observation = next((o for o in engine.observations(ref) if o['observation_id'] == scope['observation_id']), None)
        if not observation or observation['kind'] != 'MS_CENTROID':
            raise NotFound()
        run_id = observation['session_id']
        if not any(record['run_id'] == run_id for record in engine.ms.runs(ref.experiment_id)):
            raise NotFound()
        manifest, _, pin = engine.ms.read(run_id)
        if pin != observation['artifact_sha256']:
            raise Unavailable()
        if operation == 'spectrum.get':
            return engine.spectrum(ref, run_id, offset=query['offset'], limit=query['limit'])
        # The existing report builder verifies preserved source/normalized bytes
        # against the independently recorded manifest pin and Genesis history.
        report = build_report(engine.ms.manifest_path(run_id), engine.ms.events(run_id),
                              expected_manifest_sha256=pin)
        return SharedMSReport.model_validate({'format':'virtuallab-service-ms-report-v1', 'reference':ref.model_dump(),
            'observation_id':scope['observation_id'], 'run_id':run_id,
            'data_origin':manifest['data_origin'], 'epistemic_state':'UNKNOWN',
            'source_sha256':manifest['source_sha256'], 'normalized_sha256':manifest['normalized_sha256'],
            'manifest_sha256':pin, 'processing_version':manifest['processing_version'],
            'software_version':manifest['software_version'], 'summary':report['summary'],
            'acceptance_checks':report['acceptance_checks'], 'workflow_check_status':report['workflow_check_status'],
            'review_status':report['review_status'], 'verification_scope':report['verification_scope']}).model_dump()
