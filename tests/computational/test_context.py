from pathlib import Path

from virtual_lab.computational.adapters import AlphaFoldDBAdapter
from virtual_lab.computational.artifacts import execute, register
from virtual_lab.computational.context import prediction_context
from virtual_lab.computational.requests import StructureRequest
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.experiment_store import ExperimentStore


def test_vertex_context_is_scoped_verified_and_excludes_tampering(tmp_path):
    ledger = GenesisLedger(str(tmp_path / "ledger.db"))
    store = ExperimentStore(str(tmp_path / "experiments.db"))
    run = execute(StructureRequest(accession="P08100", experiment_id="exp-1", hypothesis="RHO structural context"),
                  AlphaFoldDBAdapter(lambda *a: b'[{"uniprotAccession":"P08100"}]'), tmp_path / "runs")
    register(run, ledger, store)
    assert prediction_context(ledger, store, "different-experiment") == ""
    context = prediction_context(ledger, store, "exp-1")
    assert "PREDICTED" in context and "RHO structural context" in context
    assert run.sha256 in context
    (Path(run.manifest_path).parent / "metadata.json").write_text("tampered")
    context = prediction_context(ledger, store, "exp-1")
    assert '"predictions": []' in context
    assert "RHO structural context" not in context
    store.close()
    ledger.conn.close()


def test_staged_prediction_follows_assignment(tmp_path):
    ledger = GenesisLedger(str(tmp_path / "ledger.db"))
    store = ExperimentStore(str(tmp_path / "experiments.db"))
    run = execute(StructureRequest(accession="P08100"),
                  AlphaFoldDBAdapter(lambda *a: b'[{"uniprotAccession":"P08100"}]'), tmp_path / "runs")
    observation = register(run, ledger, store)
    assert "P08100" in prediction_context(ledger, store, "")
    store.save_experiment("new-experiment", "", "", "")
    store.assign_staged_to_experiment(observation.observation_id, "new-experiment")
    assert prediction_context(ledger, store, "") == ""
    assert "P08100" in prediction_context(ledger, store, "new-experiment")
    store.close()
    ledger.conn.close()
