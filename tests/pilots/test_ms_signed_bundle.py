from pathlib import Path
import zipfile
import pytest
from nacl.signing import SigningKey
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.core.provenance_export import explain_provenance
from virtual_lab.core.trusted_signers import _REGISTRY, TrustedSigner, TrustState, SignerRole
from virtual_lab.pilots.datasets import MSDatasetService
from virtual_lab.pilots.bundles import export_signed_bundle


def test_signed_bundle_uses_external_trust_and_detects_replacement(tmp_path, monkeypatch):
    ledger = GenesisLedger(str(tmp_path/'genesis.db'))
    store = ExperimentStore(str(tmp_path/'store.db'))
    try:
        store.save_experiment('e','','','')
        svc = MSDatasetService(ledger,store,tmp_path/'runs')
        source=tmp_path/'synthetic.csv'
        source.write_text('mz,intensity\n100,1\n')
        obs=svc.import_csv(source,experiment_id='e',sample_id='s',instrument_id='i',operator_id='o',approved_nonconfidential=True)
        key=SigningKey.generate()
        with pytest.raises(ValueError,match='independent publisher'):
            export_signed_bundle(svc,obs.session_id,tmp_path/'untrusted.vlab',key)
        pk=key.verify_key.encode().hex()
        monkeypatch.setitem(_REGISTRY,pk,TrustedSigner('test-only',pk,'test',TrustState.TRUSTED,[SignerRole.BUNDLE_PUBLISHER],'2026-10-29'))
        bundle=export_signed_bundle(svc,obs.session_id,tmp_path/'signed.vlab',key)
        report=explain_provenance(str(bundle))
        assert 'Genesis hash chain: VERIFIED' in report and 'Error:' not in report
        with zipfile.ZipFile(bundle) as archive:
            files={name:archive.read(name) for name in archive.namelist()}
        files['dataset/source.csv']=b'mz,intensity\n100,2\n'
        with zipfile.ZipFile(tmp_path/'tampered.vlab','w') as archive:
            for name,raw in files.items(): archive.writestr(name,raw)
        assert 'Artifact hash mismatch' in explain_provenance(str(tmp_path/'tampered.vlab'))
        files['manifest.sig']=SigningKey.generate().sign(files['manifest.json']).signature
        with zipfile.ZipFile(tmp_path/'replacement.vlab','w') as archive:
            for name,raw in files.items(): archive.writestr(name,raw)
        assert 'Invalid manifest signature' in explain_provenance(str(tmp_path/'replacement.vlab'))
    finally:
        store.close()
        ledger.conn.close()
