"""On-demand services. AlphaFold has no inference, bulk, or database-mirroring path."""
from dataclasses import asdict, is_dataclass
from enum import Enum
import importlib.metadata
import json
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

import numpy as np

from .artifacts import write_json
from .requests import GenomeRequest, StructureRequest


class InstrumentError(RuntimeError):
    """A public, credential-free error safe to display or record."""


class InstrumentAdapter(Protocol):
    def execute(self, request, directory: Path) -> dict: ...


def _json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, Enum):
        return value.name
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_value(v) for v in value]
    # SDK annotations occasionally contain non-dataclass genome/scorer objects.
    return {"type": type(value).__name__, "representation": str(value)}


def _save_track(directory, label, track):
    values = np.asarray(track.values)
    if values.dtype.hasobject:
        raise InstrumentError("Unsupported prediction array type.")
    np.savez_compressed(directory / (label + ".npz"), values=values)
    metadata = json.loads(track.metadata.to_json(orient="split"))
    annotation = {"track_metadata": metadata, "interval": _json_value(track.interval),
                  "resolution": _json_value(getattr(track, "resolution", None)),
                  "uns": _json_value(track.uns)}
    if hasattr(track, "junctions"):
        annotation["junctions"] = _json_value(track.junctions)
    write_json(directory / (label + ".json"), annotation)
    finite = values[np.isfinite(values)]
    return {"label": label, "shape": list(values.shape), "tracks": len(track.metadata),
            "minimum": float(finite.min()) if finite.size else None,
            "maximum": float(finite.max()) if finite.size else None,
            "mean": float(finite.mean()) if finite.size else None,
            "nonfinite_values": int(values.size - finite.size)}


def _save_scores(directory, scores, prefix):
    summaries = []
    for index, score in enumerate(scores):
        label = f"{prefix}-{index}"
        values = score.X.toarray() if hasattr(score.X, "toarray") else np.asarray(score.X)
        np.savez_compressed(directory / (label + ".npz"), values=values)
        write_json(directory / (label + ".json"), {
            "genes": json.loads(score.obs.to_json(orient="split")),
            "tracks": json.loads(score.var.to_json(orient="split")),
            "uns": _json_value(score.uns),
        })
        summaries.append({"label": label, "shape": list(values.shape),
                          "scorer": _json_value(score.uns.get("scorer"))})
    return summaries


class AlphaGenomeAdapter:
    def __init__(self, client=None):
        self._client = client

    def execute(self, request: GenomeRequest, directory: Path) -> dict:
        try:
            from alphagenome.data import genome
            from alphagenome.models import dna_client, variant_scorers
        except ImportError:
            raise InstrumentError("Install the biology extra: python -m pip install -e '.[biology]'.") from None
        client = self._client
        owns_client = client is None
        try:
            if client is None:
                from virtual_lab.ai.credentials import CredentialService
                key = CredentialService().get_api_key("alphagenome")
                if not key:
                    raise InstrumentError("Save an AlphaGenome API key in the Computational Biology tab first.")
                client = dna_client.create(key, model_version=dna_client.ModelVersion[request.model_version], timeout=20)
            interval = genome.Interval(request.chromosome, request.start, request.start + request.length)
            kwargs = {"requested_outputs": [dna_client.OutputType[o] for o in request.outputs],
                      "ontology_terms": list(request.ontology_terms) or None}
            variant = None
            if request.operation in ("variant", "score"):
                variant = genome.Variant(request.chromosome, request.position,
                                         request.reference_bases, request.alternate_bases)
            summaries = []
            if request.operation in ("score", "ism"):
                scorers = [variant_scorers.RECOMMENDED_VARIANT_SCORERS[o] for o in request.outputs]
                if request.operation == "score":
                    scores = client.score_variant(interval, variant, variant_scorers=scorers)
                    summaries = _save_scores(directory, scores, "scores")
                else:
                    region = genome.Interval(request.chromosome, request.ism_start, request.ism_start + request.ism_width)
                    batches = client.score_ism_variants(interval, region, variant_scorers=scorers,
                                                        max_workers=2, progress_bar=False)
                    for index, scores in enumerate(batches):
                        summaries.extend(_save_scores(directory, scores, f"ism-{index}"))
            else:
                if request.operation == "variant":
                    result = client.predict_variant(interval, variant, **kwargs)
                    predictions = {"reference": result.reference, "alternate": result.alternate}
                elif request.operation == "sequence":
                    predictions = {"sequence": client.predict_sequence(request.sequence, **kwargs)}
                else:
                    predictions = {"reference": client.predict_interval(interval, **kwargs)}
                for allele, prediction in predictions.items():
                    for output in kwargs["requested_outputs"]:
                        track = prediction.get(output)
                        if track is None or len(track.metadata) == 0:
                            raise InstrumentError(f"No {output.name} tracks returned for the selected biological context.")
                        summaries.append(_save_track(directory, f"{allele}-{output.name.lower()}", track))
            if not summaries:
                raise InstrumentError("AlphaGenome returned no predictions or scores.")
            return {"provider": "Google DeepMind AlphaGenome",
                    "source": "https://gdmscience.googleapis.com",
                    "client_version": importlib.metadata.version("alphagenome"),
                    "model_version": request.model_version,
                    "summary": {"operation": request.operation, "outputs": summaries},
                    "limitations": [
                        "Model predictions are not experimental measurements or clinical conclusions.",
                        "hg38; interval starts are 0-based, variant positions are 1-based.",
                        "Supplied reference alleles are not independently checked against hg38 by this adapter.",
                        "Track magnitude is not a calibrated probability or confidence score.",
                        "Model selector and SDK version are recorded; the service does not expose an immutable weight digest.",
                        "Gene/transcript/protein mapping requires explicit biological annotation; no automatic structural effect is inferred.",
                    ]}
        except InstrumentError:
            raise
        except Exception as exc:
            # Remote exceptions can include authentication metadata. Never expose their text.
            code = getattr(exc, "code", lambda: None)()
            status = getattr(code, "name", type(exc).__name__)
            raise InstrumentError(f"AlphaGenome request failed ({status}). Check the key, inputs, quota, and network.") from None
        finally:
            if owns_client and client is not None:
                # SDK 0.9 exposes the channel only through this private attribute.
                client._channel.close()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InstrumentError("Unexpected redirect from AlphaFold; no file was retrieved.")


def fetch_alphafold(url: str, limit: int) -> bytes:
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.netloc != "alphafold.ebi.ac.uk" or
            not parts.path.startswith(("/api/prediction/", "/files/")) or parts.query or parts.fragment):
        raise InstrumentError("AlphaFold returned an unsupported download URL.")
    try:
        with build_opener(_NoRedirect()).open(Request(url, headers={"User-Agent": "VirtualLab/1.0"}), timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > limit:
                raise InstrumentError("This individual AlphaFold file exceeds the download size limit.")
            payload = response.read(limit + 1)
            if len(payload) > limit:
                raise InstrumentError("This individual AlphaFold file exceeds the download size limit.")
            return payload
    except HTTPError as exc:
        if exc.code == 404:
            raise InstrumentError("No AlphaFold prediction was found for that accession or file.") from None
        raise InstrumentError(f"AlphaFold returned HTTP {exc.code}.") from None
    except (URLError, TimeoutError, OSError):
        raise InstrumentError("AlphaFold could not be reached. Check the network and retry.") from None


class AlphaFoldDBAdapter:
    def __init__(self, fetch=fetch_alphafold):
        self.fetch = fetch

    def execute(self, request: StructureRequest, directory: Path) -> dict:
        url = "https://alphafold.ebi.ac.uk/api/prediction/" + request.accession
        raw = self.fetch(url, 2 * 1024 * 1024)
        entries = json.loads(raw)
        if not isinstance(entries, list) or not entries or any(not isinstance(e, dict) for e in entries):
            raise InstrumentError("AlphaFold returned no usable prediction metadata.")
        if any(e.get("uniprotAccession") != request.accession for e in entries):
            raise InstrumentError("AlphaFold returned a different accession; explicit identifier mapping is required.")
        if len(entries) != 1 and (request.include_structure or request.include_pae):
            raise InstrumentError("Multiple models exist. Retrieve metadata only and select the appropriate model separately.")
        (directory / "metadata.json").write_bytes(raw)
        summary = {"accession": request.accession, "models": [
            {"entry_id": e.get("modelEntityId", e.get("entryId")), "gene": e.get("gene"),
             "description": e.get("uniprotDescription"), "version": e.get("latestVersion"),
             "mean_plddt": e.get("globalMetricValue"), "sequence_start": e.get("sequenceStart", e.get("uniprotStart")),
             "sequence_end": e.get("sequenceEnd", e.get("uniprotEnd"))}
            for e in entries]}
        if request.include_structure:
            if not entries[0].get("cifUrl"):
                raise InstrumentError("No mmCIF structure is available for this entry.")
            (directory / "structure.cif").write_bytes(self.fetch(entries[0]["cifUrl"], 16 * 1024 * 1024))
        if request.include_pae:
            if not entries[0].get("paeDocUrl"):
                raise InstrumentError("No PAE file is available for this entry.")
            pae_raw = self.fetch(entries[0]["paeDocUrl"], 32 * 1024 * 1024)
            pae = np.asarray(json.loads(pae_raw)[0]["predicted_aligned_error"], dtype=float)
            if pae.ndim != 2 or not pae.size or pae.shape[0] != pae.shape[1] or not np.isfinite(pae).all() or (pae < 0).any():
                raise InstrumentError("AlphaFold returned an invalid PAE matrix.")
            summary["pae"] = {"shape": list(pae.shape), "mean_angstrom": float(pae.mean()), "max_angstrom": float(pae.max())}
            (directory / "pae.json").write_bytes(pae_raw)
        return {"provider": "EMBL-EBI AlphaFold Protein Structure Database", "source": url,
                "model_version": [e.get("latestVersion") for e in entries], "summary": summary,
                "limitations": [
                    "This is retrieval of existing predicted structures, not new structure inference.",
                    "The retrieved protein model does not establish a variant-induced structural change.",
                    "pLDDT describes local confidence; PAE describes relative positional uncertainty in angstroms.",
                    "Confidence is not experimental validation or a probability of biological function.",
                ]}


def adapter_for(request) -> InstrumentAdapter:
    if isinstance(request, GenomeRequest):
        return AlphaGenomeAdapter()
    if isinstance(request, StructureRequest):
        return AlphaFoldDBAdapter()
    raise ValueError("Unsupported instrument request.")
