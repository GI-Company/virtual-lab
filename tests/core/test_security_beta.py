"""Adversarial and compatibility checks for shared beta boundaries."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import pytest
from nacl.signing import SigningKey
from virtual_lab.core.canonical import canonical_json, legacy_canonical_json, strict_json_loads
from virtual_lab.core.ledger import Actor, GenesisLedger, LedgerEvent, ChainIntegrityError, read_ledger_events
from virtual_lab.domain.approval_policy import Proposal, ApprovalPolicy


def test_jcs_vectors_and_ambiguous_json():
    assert canonical_json([-0.0, 1.0, 1e-6, 1e20, 1e21]) == b'[0,1,0.000001,100000000000000000000,1e+21]'
    assert canonical_json({'\ue000': 1, '\U0001f600': 2}).decode() == '{"😀":2,"\ue000":1}'
    for raw in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
        with pytest.raises(ValueError): strict_json_loads(raw)
    for value in [float('nan'), float('inf'), 2**64]:
        with pytest.raises(ValueError): canonical_json(value)


@pytest.mark.parametrize('normalize', [False, True])
def test_historical_rows_unchanged_on_schema_upgrade(tmp_path, normalize):
    path = tmp_path / 'old.db'
    event = LedgerEvent(schema_version='1.0', sequence=0, event_id='GENESIS', timestamp_utc='2026-01-01T00:00:00Z',
        actor=Actor(type='SYSTEM', id='genesis'), event_type='LEDGER_INITIALIZED', payload={'zero': -0.0, 'one': 1.0}, parent_hash='0'*64)
    encoded = legacy_canonical_json(event.model_dump(exclude={'event_hash'}), normalize_zero=normalize)
    digest = hashlib.sha256(encoded).hexdigest()
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE ledger_events (sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE, timestamp_utc TEXT, actor_type TEXT, actor_id TEXT, event_type TEXT, payload_json TEXT, parent_hash TEXT, event_hash TEXT, schema_version TEXT)')
        conn.execute('INSERT INTO ledger_events VALUES (?,?,?,?,?,?,?,?,?,?)',
            (0, event.event_id, event.timestamp_utc, 'SYSTEM','genesis', event.event_type,
             json.dumps(event.payload), event.parent_hash, digest, '1.0'))
        before = conn.execute('SELECT * FROM ledger_events').fetchall()
    ledger = GenesisLedger(str(path))
    assert ledger.get_head().event_hash == digest
    # Original columns retain their exact values, including historical JSON bytes.
    assert tuple(ledger.conn.execute('SELECT sequence,event_id,timestamp_utc,actor_type,actor_id,event_type,payload_json,parent_hash,event_hash,schema_version FROM ledger_events').fetchone()) == before[0]
    ledger.append('new', Actor(type='USER', id='test'), 'TEST', {'n': 1.0})
    ledger.conn.close()
    events = read_ledger_events(path)
    assert [e.schema_version for e in events] == ['1.0', '2.0']
    assert events[0].event_hash == digest


def test_invalid_history_is_not_repaired(tmp_path):
    path = tmp_path/'broken.db'; ledger=GenesisLedger(str(path)); ledger.conn.close()
    with sqlite3.connect(path) as conn:
        conn.execute('DROP TRIGGER prevent_ledger_update')
        conn.execute("UPDATE ledger_events SET payload_json='{}'")
    before=path.read_bytes()
    with pytest.raises(ChainIntegrityError): GenesisLedger(str(path))
    assert path.read_bytes() == before


def provision(tmp_path, monkeypatch):
    from virtual_lab.core.trusted_signers import _REGISTRY, TrustedSigner, TrustState, SignerRole
    key=SigningKey.generate(); public=key.verify_key.encode().hex()
    monkeypatch.setitem(_REGISTRY, public, TrustedSigner('operator', public, 'test', TrustState.TRUSTED, [SignerRole.HUMAN_APPROVAL], 'test'))
    now=datetime.now(timezone.utc)
    proposal=Proposal('proposal', 'TEST', {'value':1.0}, 'scratch', 'assistant',
        (now-timedelta(seconds=1)).isoformat(), (now+timedelta(hours=1)).isoformat(), 'unique-nonce')
    path=tmp_path/'approval.db'; ledger=GenesisLedger(str(path)); policy=ApprovalPolicy(ledger)
    signature=policy.sign_proposal(proposal,key)
    ledger.append('p', Actor(type='AI',id='assistant'),'AI_PROPOSAL',asdict(proposal))
    ledger.append('r',Actor(type='SYSTEM',id='rules'),'RULE_EVALUATION',{'proposal_id':proposal.proposal_id,'passed':True})
    ledger.append('d',Actor(type='HUMAN',id='operator'),'HUMAN_DECISION',{'proposal_id':proposal.proposal_id,'decision':'APPROVED','signature':signature.hex()})
    ledger.conn.close()
    return path,proposal,signature,key.verify_key.encode()


def test_durable_claim_survives_callback_failure_and_restart(tmp_path, monkeypatch):
    path, proposal, signature, public=provision(tmp_path, monkeypatch)
    effects=[]
    def fail(p): effects.append(p.proposal_id); raise RuntimeError('simulated post-side-effect failure')
    ledger=GenesisLedger(str(path))
    with pytest.raises(RuntimeError): ApprovalPolicy(ledger).verify_and_execute(proposal,signature,public,fail)
    ledger.conn.close()
    ledger=GenesisLedger(str(path))
    with pytest.raises(ValueError,match='ALREADY_EXECUTED_OR_CLAIMED'):
        ApprovalPolicy(ledger).verify_and_execute(proposal,signature,public,lambda p: effects.append('replay'))
    ledger.conn.close()
    assert effects==['proposal']
    assert {'ACTION_CLAIMED','ACTION_FAILED'} <= {e.event_type for e in read_ledger_events(path)}


def test_concurrent_approval_consumed_once(tmp_path, monkeypatch):
    path,proposal,signature,public=provision(tmp_path,monkeypatch)
    barrier=threading.Barrier(2); effects=[]
    def execute(_):
        ledger=GenesisLedger(str(path)); barrier.wait()
        try:
            ApprovalPolicy(ledger).verify_and_execute(proposal,signature,public,lambda p:effects.append(p.proposal_id))
            return 'executed'
        except ValueError as error: return str(error)
        finally: ledger.conn.close()
    with ThreadPoolExecutor(2) as pool: outcomes=list(pool.map(execute,range(2)))
    assert effects==['proposal'] and outcomes.count('executed')==1
    assert any('ALREADY_EXECUTED' in outcome for outcome in outcomes)
    read_ledger_events(path)


def test_exposed_publisher_revoked_and_no_implicit_private_key(tmp_path, monkeypatch):
    from virtual_lab.core.trusted_signers import verify_signer_role, SignerRole
    from scripts.build_vlab_bundle import build_vlab_bundle
    compromised='414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935'
    assert not verify_signer_role(compromised,SignerRole.BUNDLE_PUBLISHER)
    assert not verify_signer_role(compromised,SignerRole.PROGRAM_SIGNER)
    monkeypatch.delenv('VLAB_PUBLISHER_SK',raising=False)
    with pytest.raises(ValueError,match='explicitly'): build_vlab_bundle(str(tmp_path),str(tmp_path/'out.vlab'))
    assert not (tmp_path/'out.vlab').exists()


def test_snapshot_includes_live_wal_and_not_itself(tmp_path, trusted_publisher):
    from scripts.build_vlab_bundle import build_vlab_bundle
    from virtual_lab.core.provenance_export import explain_provenance
    import zipfile
    ledger=GenesisLedger(str(tmp_path/'genesis.db'))
    ledger.append('wal-record',Actor(type='USER',id='test'),'TEST',{'test':'wal'})
    target=tmp_path/'output.vlab';build_vlab_bundle(str(tmp_path),str(target))
    build_vlab_bundle(str(tmp_path),str(target))
    with zipfile.ZipFile(target) as package:
        assert 'output.vlab' not in package.namelist()
        assert not any(name.endswith(('-wal','-shm')) for name in package.namelist())
    report=explain_provenance(str(target))
    assert 'Genesis hash chain: VERIFIED' in report and 'Error:' not in report
    with zipfile.ZipFile(target) as package:
        extracted=tmp_path/'snapshot.db';extracted.write_bytes(package.read('genesis.db'))
    assert read_ledger_events(extracted)[-1].event_id=='wal-record'
    ledger.conn.close()


def test_two_ledgers_keep_colliding_ids_and_original_history(tmp_path):
    from virtual_lab.gui.services.run_store import RunStore
    hashes=[]
    for name in ['genesis.db','ledger.db']:
        ledger=GenesisLedger(str(tmp_path/name))
        ledger.append('same-id',Actor(type='USER',id='test'),'TEST',{'source':name})
        ledger.conn.close();hashes.append(hashlib.sha256((tmp_path/name).read_bytes()).hexdigest())
    events=RunStore(tmp_path).events()
    matching=[e for e in events if e['event_id']=='same-id']
    assert len(matching)==2 and len({e['event_key'] for e in matching})==2
    assert hashes==[hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in ['genesis.db','ledger.db']]


def test_rho_perturbs_only_declared_controls():
    from virtual_lab.gui.services.simulation_runner import run_simulation,RunConfig
    from virtual_lab.models.registry import get_model
    result=run_simulation(RunConfig(duration_h=1,members=4))
    assert set(result['parameter_samples']) == {p.key for p in get_model('rho_p23h').parameters}
    assert len(result['parameter_samples'])==4 and result['numerical_check']['status']=='PASSED'


def test_timestamp_is_in_provenance_hash():
    from virtual_lab.core.provenance import ProvenanceTracker
    tracker=ProvenanceTracker();tracker.record('test',{'value':1.0})
    original,content=tracker.generate_hash(),tracker.generate_content_hash()
    tracker.history[0].timestamp='2099-01-01T00:00:00Z'
    assert tracker.generate_hash()!=original and tracker.generate_content_hash()==content


def test_explicit_operator_trust_cannot_restore_revoked_key(tmp_path,monkeypatch):
    from virtual_lab.core.trusted_signers import verify_signer_role,SignerRole
    key=SigningKey.generate().verify_key.encode().hex()
    revoked='414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935'
    path=tmp_path/'trust.json';path.write_text(json.dumps({'format':'vlab-trust-v1','signers':[
        {'signer_id':'operator','public_key_hex':public,'roles':['BUNDLE_PUBLISHER']} for public in [key,revoked]]}))
    monkeypatch.setenv('VIRTUALLAB_TRUST_STORE',str(path))
    assert verify_signer_role(key,SignerRole.BUNDLE_PUBLISHER)
    assert not verify_signer_role(key,SignerRole.PROGRAM_SIGNER)
    assert not verify_signer_role(revoked,SignerRole.BUNDLE_PUBLISHER)


def test_edition_manifest_selects_isolated_default(monkeypatch,tmp_path):
    from virtual_lab.edition import current_edition,EDITIONS
    from virtual_lab.core.paths import app_data_dir
    monkeypatch.delenv('VIRTUALLAB_EDITION',raising=False)
    packaged=json.loads((Path(__file__).parents[2]/'virtual_lab/beta_edition.json').read_text())['edition']
    assert current_edition()==packaged and packaged in EDITIONS
    monkeypatch.delenv('VIRTUALLAB_DATA_DIR',raising=False)
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    for edition in EDITIONS:
        monkeypatch.setenv('VIRTUALLAB_EDITION',edition)
        assert app_data_dir().parts[-2:]==('beta',edition)
    monkeypatch.setenv('VIRTUALLAB_EDITION','typo')
    with pytest.raises(ValueError): app_data_dir()


def test_provenance_ui_displays_both_ledger_sources(qtbot,tmp_path,monkeypatch):
    from virtual_lab.gui.provenance.provenance_workspace import ProvenanceWorkspace
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    monkeypatch.setenv('VIRTUALLAB_DATA_DIR',str(tmp_path))
    for name in ['ledger.db','genesis.db']:
        ledger=GenesisLedger(str(tmp_path/name));ledger.append('collision',Actor(type='USER',id='test'),'TEST',{})
        ledger.conn.close()
    panel=ProvenanceWorkspace(WorkspaceState());qtbot.addWidget(panel)
    assert len([e for e in panel.events if e['event_id']=='collision'])==2
    labels=[panel.event_list.item(i).text() for i in range(panel.event_list.count())]
    assert any(s.startswith('ledger.db /') for s in labels) and any(s.startswith('genesis.db /') for s in labels)
