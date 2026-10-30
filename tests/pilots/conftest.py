import pytest
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.pilots.datasets import MSDatasetService

@pytest.fixture
def service(tmp_path):
    ledger = GenesisLedger(str(tmp_path/'genesis.db'))
    store = ExperimentStore(str(tmp_path/'experiments.db'))
    store.save_experiment('exp', '', '', '', label='Synthetic MS workflow')
    svc = MSDatasetService(ledger, store, tmp_path/'runs')
    yield svc
    store.close()
    ledger.conn.close()

