"""Scoped signed .vlab export using the existing canonical JSON and verifier.

Signing requires a caller-supplied private key and an independently configured
publisher trust anchor. Public demonstration keys are deliberately refused.
"""
import io
from pathlib import Path
import tempfile
import zipfile
from virtual_lab.core.canonical import canonical_json
from virtual_lab.core.ledger import GenesisLedger, Actor
from virtual_lab.core.trusted_signers import verify_signer_role, SignerRole
from virtual_lab.pilots.ms_workflow import _sha256, json_bytes
from virtual_lab.pilots.storage import checked_path, read_bounded
from virtual_lab.pilots.schemas import MAX_SOURCE_BYTES, MAX_MANIFEST_BYTES, PilotError

DEMO_PUBLIC_KEY = '414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935'


def export_signed_bundle(service, run_id, destination, signing_key):
    service.require_export(run_id)
    from virtual_lab.gui.services.research_outputs import publish_new_file
    from virtual_lab.pilots.reporting import build_report
    public_key = signing_key.verify_key.encode().hex()
    if public_key == DEMO_PUBLIC_KEY or not verify_signer_role(public_key, SignerRole.BUNDLE_PUBLISHER):
        raise PilotError('UNTRUSTED_SIGNER', 'Configure an independent publisher trust anchor; demonstration keys cannot sign pilot exports')
    _, snapshot, pin = service.read(run_id)
    destination = checked_path(destination)
    if destination.suffix != '.vlab':
        raise PilotError('EXPORT_FORMAT', 'Choose a new .vlab filename')
    path = service.manifest_path(run_id)
    events = service.events(run_id)
    files = snapshot
    files = {'dataset/'+name: raw for name,raw in files.items()}
    files['report.json'] = json_bytes(build_report(path, events, expected_manifest_sha256=pin))
    # A fresh export ledger references only this run's original events, avoiding
    # disclosure of unrelated studies in the application's shared ledger.
    with tempfile.TemporaryDirectory(prefix='.ms-export-', dir=service.root) as temporary:
        ledger = GenesisLedger(str(Path(temporary)/'genesis.db'))
        try:
            for event in events:
                ledger.append(event['event_id'], Actor(**event['actor']), 'MS_SOURCE_EVENT_REFERENCED',
                    {'original_event': event, 'scope': 'Export reference; original local ledger not included'})
            ledger.conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        finally:
            ledger.conn.close()
        files['genesis.db'] = read_bounded(Path(temporary)/'genesis.db', MAX_SOURCE_BYTES)
    manifest = {'vlab_version':'1.0', 'publisher_public_key':public_key,
        'build_utc': events[-1]['timestamp_utc'], 'contents':
        [{'path':name,'sha256':_sha256(raw)} for name,raw in sorted(files.items())]}
    content = canonical_json(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr('manifest.json', content)
        archive.writestr('manifest.sig', signing_key.sign(content).signature)
    result = publish_new_file(destination, buffer.getvalue())
    service._event('MS_DATASET_EXPORTED', {'run_id':run_id, 'format':'.vlab', 'report_sha256':_sha256(buffer.getvalue()),
        'publisher_public_key':public_key, 'manifest_sha256':service._record(run_id)['manifest_sha256']})
    return result
