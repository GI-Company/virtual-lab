import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from virtual_lab.computational import adapters
from virtual_lab.computational.adapters import AlphaFoldDBAdapter, AlphaGenomeAdapter, InstrumentError
from virtual_lab.computational.artifacts import CompletedRun, execute, register
from virtual_lab.computational.requests import GenomeRequest, StructureRequest
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.epistemics import EpistemicState
from virtual_lab.domain.experiment_store import ExperimentStore


def metadata():
    return [{"uniprotAccession": "P08100", "modelEntityId": "AF-P08100-F1", "latestVersion": 6,
             "globalMetricValue": 88.75, "cifUrl": "https://alphafold.ebi.ac.uk/files/example.cif",
             "paeDocUrl": "https://alphafold.ebi.ac.uk/files/example.json"}]


@pytest.mark.parametrize("fields", [
    {"length": 16000}, {"outputs": ()}, {"outputs": ("made-up",)},
    {"ontology_terms": ("retina",)}, {"start": -1},
    {"operation": "sequence", "sequence": "ACGT"},
    {"operation": "variant", "position": 10, "reference_bases": "A", "alternate_bases": "A"},
    {"operation": "variant", "position": 16384, "reference_bases": "AC", "alternate_bases": "T"},
    {"operation": "ism", "ism_start": 0, "ism_width": 33},
    {"operation": "ism", "ism_start": 16384},
    {"operation": "score", "position": 10, "reference_bases": "A", "alternate_bases": "T", "ontology_terms": ("CL:0000540",)},
    {"api_key": "must-not-enter-the-request"},
])
def test_invalid_genome_requests(fields):
    with pytest.raises(ValidationError):
        GenomeRequest.model_validate({"operation": "interval", **fields})


def test_coordinate_boundaries():
    for position in (1, 16384):
        GenomeRequest(operation="variant", position=position, reference_bases="A", alternate_bases="T")
    with pytest.raises(ValidationError):
        GenomeRequest(operation="variant", position=16385, reference_bases="A", alternate_bases="T")


@pytest.mark.parametrize("accession", ["../P08100", "P08100,P12345", "https://example.org", "P08100?x=1", ""])
def test_no_bulk_or_url_inputs(accession):
    with pytest.raises(ValidationError):
        StructureRequest(accession=accession)


def test_metadata_only_never_downloads_structures(tmp_path):
    urls = []
    def fetch(url, limit):
        urls.append(url)
        return json.dumps(metadata()).encode()
    result = execute(StructureRequest(accession="P08100"), AlphaFoldDBAdapter(fetch), tmp_path)
    manifest = result.read()
    assert urls == ["https://alphafold.ebi.ac.uk/api/prediction/P08100"]
    assert [a["file"] for a in manifest["artifacts"]] == ["metadata.json"]
    assert manifest["epistemic_state"] == "PREDICTED"
    assert manifest["model_version"] == [6]


def test_single_structure_and_pae_are_opt_in(tmp_path):
    responses = [json.dumps(metadata()).encode(), b"data_example\n", json.dumps([{"predicted_aligned_error": [[0, 2], [3, 0]]}]).encode()]
    calls = []
    def fetch(url, limit):
        calls.append((url, limit))
        return responses[len(calls) - 1]
    result = execute(StructureRequest(accession="P08100", include_structure=True, include_pae=True), AlphaFoldDBAdapter(fetch), tmp_path)
    assert len(calls) == 3
    assert result.read()["summary"]["pae"]["mean_angstrom"] == 1.25


@pytest.mark.parametrize("url", ["http://alphafold.ebi.ac.uk/files/a", "https://evil.example/a",
                                    "https://alphafold.ebi.ac.uk@evil.example/files/a", "https://alphafold.ebi.ac.uk/files/a?redirect=1"])
def test_untrusted_download_urls_are_rejected(url):
    with pytest.raises(InstrumentError, match="unsupported"):
        adapters.fetch_alphafold(url, 100)


def test_size_limit_checks_even_without_content_length(monkeypatch):
    class Response(io.BytesIO):
        headers = {}
    monkeypatch.setattr(adapters, "build_opener", lambda *a: SimpleNamespace(open=lambda *a, **kw: Response(b"12345")))
    with pytest.raises(InstrumentError, match="size limit"):
        adapters.fetch_alphafold("https://alphafold.ebi.ac.uk/files/a", 4)


def test_ambiguous_or_mismatched_accession_is_not_silently_selected(tmp_path):
    for records in ([{**metadata()[0], "uniprotAccession": "Q99999"}], metadata() * 2):
        with pytest.raises(InstrumentError):
            execute(StructureRequest(accession="P08100", include_structure=True),
                    AlphaFoldDBAdapter(lambda *a: json.dumps(records).encode()), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_register_and_retrieve_prediction_preserves_epistemic_state(tmp_path):
    ledger = GenesisLedger(str(tmp_path / "ledger.db"))
    store = ExperimentStore(str(tmp_path / "experiments.db"))
    request = StructureRequest(accession="P08100", experiment_id="EXP-1", hypothesis="Explicit hypothesis")
    run = execute(request, AlphaFoldDBAdapter(lambda *a: json.dumps(metadata()).encode()), tmp_path / "runs")
    obs = register(run, ledger, store)
    register(run, ledger, store)
    loaded = store.get_observations_for_experiment("EXP-1")
    assert len(loaded) == 1
    assert loaded[0].epistemic_state == EpistemicState.PREDICTED
    assert loaded[0].artifact_sha256 == obs.artifact_sha256
    assert ledger.conn.execute("SELECT COUNT(*) FROM ledger_events WHERE event_type = 'COMPUTATIONAL_PREDICTION_RECORDED'").fetchone()[0] == 1
    ledger.verify_chain()
    store.close()
    ledger.conn.close()


def test_staging_and_tamper_detection(tmp_path):
    run = execute(StructureRequest(accession="P08100"), AlphaFoldDBAdapter(lambda *a: json.dumps(metadata()).encode()), tmp_path / "runs")
    ledger = GenesisLedger(str(tmp_path / "ledger.db"))
    store = ExperimentStore(str(tmp_path / "experiments.db"))
    register(run, ledger, store)
    assert store.list_staged()[0]["epistemic_state"] == "PREDICTED"
    (Path(run.manifest_path).parent / "metadata.json").write_text("tampered")
    with pytest.raises(ValueError, match="integrity"):
        register(run, ledger, store)
    with pytest.raises(ValueError, match="manifest hash"):
        CompletedRun(run.manifest_path, "0" * 64).read()
    store.close()
    ledger.conn.close()


def test_variant_arrays_and_annotation_round_trip(tmp_path):
    pd = pytest.importorskip("pandas")
    dna_output = pytest.importorskip("alphagenome.models.dna_output")
    from alphagenome.data import genome, track_data
    track = track_data.TrackData(values=np.array([[1.], [2.]], dtype=np.float32),
                                 metadata=pd.DataFrame({"name": ["test-track"], "strand": ["+"]}),
                                 interval=genome.Interval("chr1", 0, 2), resolution=1)
    class Client:
        def predict_variant(self, interval, variant, **kwargs):
            assert interval.start == 0 and interval.end == 16384
            assert variant.position == 1
            assert kwargs["ontology_terms"] == ["CL:0000540"]
            return dna_output.VariantOutput(reference=dna_output.Output(rna_seq=track), alternate=dna_output.Output(rna_seq=track))
    request = GenomeRequest(position=1, reference_bases="A", alternate_bases="T", ontology_terms=("CL:0000540",))
    run = execute(request, AlphaGenomeAdapter(Client()), tmp_path)
    manifest = run.read()
    assert len(manifest["artifacts"]) == 4
    np.testing.assert_array_equal(np.load(Path(run.manifest_path).parent / "reference-rna_seq.npz")["values"], track.values)
    annotations = json.loads((Path(run.manifest_path).parent / "reference-rna_seq.json").read_text())
    assert annotations["track_metadata"]["data"][0][0] == "test-track"
    assert annotations["interval"]["start"] == 0


def test_remote_errors_do_not_expose_authentication(tmp_path):
    pytest.importorskip("alphagenome")
    class Client:
        def predict_interval(self, *args, **kwargs):
            raise RuntimeError("secret-key-in-provider-error")
    with pytest.raises(InstrumentError) as caught:
        execute(GenomeRequest(operation="interval"), AlphaGenomeAdapter(Client()), tmp_path)
    assert "secret-key" not in str(caught.value)
    assert list(tmp_path.iterdir()) == []
