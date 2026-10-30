import os
from pathlib import Path
import subprocess
import sys
import pytest
from virtual_lab.pilots.lease import WorkspaceLease
from virtual_lab.pilots.schemas import PilotError


def test_second_process_cannot_recover_an_active_import(service):
    run = service.root/'active'
    run.mkdir()
    manifest = run/'manifest.json'
    manifest.write_text('{"live":"import"}')
    service._event('MS_DATASET_REGISTERED', {'run_id':'active'})
    script = '''
import sys
from pathlib import Path
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.pilots.datasets import MSDatasetService
from virtual_lab.pilots.schemas import PilotError
root=Path(sys.argv[1])
ledger=GenesisLedger(str(root/'genesis.db'))
store=ExperimentStore(str(root/'experiments.db'))
try:
    service=MSDatasetService(ledger,store,root/'runs')
except PilotError as error:
    assert error.code=='WORKSPACE_BUSY', str(error)
    print('WORKSPACE_BUSY')
else:
    service.close()
    raise AssertionError('A second process obtained the writer lease')
finally:
    store.close()
    ledger.conn.close()
'''
    result = subprocess.run([sys.executable,'-c',script,str(service.root.parent)], capture_output=True,text=True,timeout=20)
    assert result.returncode==0, result.stdout+result.stderr
    assert 'WORKSPACE_BUSY' in result.stdout
    assert manifest.read_text()=='{"live":"import"}'
    assert service.events('active')[-1]['event_type']=='MS_DATASET_REGISTERED'


def test_busy_lease_and_release_without_deleting_lock_file(tmp_path):
    first=WorkspaceLease(tmp_path)
    with pytest.raises(PilotError) as error:
        WorkspaceLease(tmp_path)
    assert error.value.code=='WORKSPACE_BUSY'
    first.close()
    first.close()
    assert (tmp_path/'.workspace-writer.lock').is_file()
    with WorkspaceLease(tmp_path) as second:
        assert second.active
    assert not second.active


def test_failed_service_construction_releases_lease(tmp_path):
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.pilots.datasets import MSDatasetService
    ledger=GenesisLedger(str(tmp_path/'genesis.db'))
    store=ExperimentStore(str(tmp_path/'experiments.db'))
    invalid=tmp_path/'not-a-directory'
    invalid.write_text('occupied')
    try:
        with pytest.raises(OSError):
            MSDatasetService(ledger,store,invalid)
        with WorkspaceLease(tmp_path):
            pass
    finally:
        store.close()
        ledger.conn.close()


def test_linked_lock_file_rejected(tmp_path):
    outside=tmp_path/'outside'
    outside.write_text('preserve')
    (tmp_path/'.workspace-writer.lock').symlink_to(outside)
    with pytest.raises(PilotError) as error:
        WorkspaceLease(tmp_path)
    assert error.value.code=='UNSAFE_PATH'
    assert outside.read_text()=='preserve'


def test_private_posix_workspace_permissions(tmp_path):
    if os.name=='nt':
        pytest.skip('POSIX mode bits; Windows ACLs are a deployment responsibility')
    root=tmp_path/'workspace'
    with WorkspaceLease(root):
        assert root.stat().st_mode & 0o777 == 0o700
        assert (root/'.workspace-writer.lock').stat().st_mode & 0o777 == 0o600
