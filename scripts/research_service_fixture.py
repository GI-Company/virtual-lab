"""Explicit synthetic qualification fixture; never loads a user's workspace."""
from dataclasses import dataclass
import json
from pathlib import Path
import time
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from virtual_lab.application.engine import ResearchEngine
from virtual_lab.pilots.storage import write_private
from virtual_lab.integrations.research_service.auth import TokenVerifier
from virtual_lab.integrations.research_service.policy import AccessPolicy, Grant

ISSUER = 'https://synthetic-issuer.invalid'
AUDIENCE = 'virtuallab-synthetic-research-service'


@dataclass
class SyntheticFixture:
    root: Path
    policy_path: Path
    audit_path: Path
    identity_path: Path
    private_key: object
    public_pem: str
    reference: dict
    unrelated_reference: dict
    observation: dict
    unrelated_observation: dict
    numerical_observation_id: str

    @property
    def verifier(self):
        return TokenVerifier(issuer=ISSUER, audience=AUDIENCE, public_keys={'fixture-key':self.public_pem})

    def token(self, subject='synthetic-user-a', **overrides):
        now = int(time.time())
        claims = {'iss':ISSUER,'aud':AUDIENCE,'sub':subject,'iat':now,'exp':now+300,'jti':str(uuid.uuid4())}
        claims.update(overrides)
        return jwt.encode(claims, self.private_key, algorithm='RS256', headers={'kid':'fixture-key'})

    @property
    def prefix(self):
        r = self.reference
        return f"/v1/instances/{r['instance_id']}/projects/{r['project_id']}"

    @property
    def experiment_url(self):
        return self.prefix+'/experiments/'+self.reference['experiment_id']

    @property
    def report_url(self):
        return self.experiment_url+'/observations/'+self.observation['observation_id']+'/report'


def seed_synthetic_fixture(directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700)  # Refuse reuse and accidental desktop roots.
    root = directory/'synthetic-instance'
    with_engine = ResearchEngine(root)
    try:
        engine = with_engine
        refs, observations = [], []
        for suffix in ('a','b'):
            project = engine.create_project('Synthetic service qualification '+suffix)
            ref = engine.create_experiment(project['id'], 'Synthetic centroid software test', 'Do byte-integrity and access checks hold?')
            refs.append(ref.model_dump())
            raw = ('mz,intensity\n'+''.join(f'{100+i/10:.1f},{(i*37)%997+1}\n' for i in range(128))).encode()
            observation = engine.import_spectrum(ref, raw, dataset_id='synthetic-'+suffix,
                sample_id='synthetic-sample',instrument_id='synthetic-no-instrument',
                operator_id='private-fixture-operator',approved_nonconfidential=True,data_origin='synthetic')
            observations.append(observation)
            engine.ms.reprocess(observation['session_id'])
            assert engine.ms.test_alteration(observation['session_id'])['detected']
            engine.ms.review(observation['session_id'],reviewer='fixture-workflow-reviewer',
                approved=True,note='Synthetic software checks only; no scientific validation')
        job = engine.submit_simulation(refs[0], {'model_id':'gene_expression','members':3,'duration_h':1}, request_id='synthetic-fixture-job')
        deadline = time.monotonic()+20
        while job.state == 'RUNNING' and time.monotonic() < deadline:
            time.sleep(.01)
            job = engine.job(refs[0], job.id)
        if job.state != 'COMPLETED':
            raise RuntimeError('Synthetic numerical fixture did not complete')
        settings = engine.settings.repository.load()
        settings.allow_cloud = True  # Explicit consent only in this newly created fixture.
        engine.settings.repository.save(settings)
    finally:
        with_engine.close()
    policy_path = directory/'service-access.json'
    policy = AccessPolicy(instance_id=refs[0]['instance_id'],enabled=True,grants=[
        Grant(subject='synthetic-user-'+suffix,tenant_id='synthetic-tenant-'+suffix,project_id=ref['project_id'],
              research_access=True,metadata=True,reports=True,spectrum=True,changes=True)
        for suffix,ref in zip(('a','b'),refs)])
    write_private(policy_path, policy.model_dump_json(indent=2).encode())
    private_key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pem = private_key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    identity_path = directory/'identity.json'
    write_private(identity_path,json.dumps({'issuer':ISSUER,'audience':AUDIENCE,'public_keys':{'fixture-key':pem}}).encode())
    return SyntheticFixture(root,policy_path,directory/'service-audit.jsonl',identity_path,private_key,pem,
        refs[0],refs[1],observations[0],observations[1],job.result_observation_id)
