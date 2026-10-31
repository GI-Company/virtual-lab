"""Verify the supplied BSA archive and exercise the existing offline MS workflow.

No archive code is executed. Measurements stay outside Git and remain UNKNOWN.
Usage: python scripts/verify_bsa_workflow.py --archive PATH --output NEW_DIRECTORY
Add --pdf for plotted PDF + JSON + detached SHA-256 exports.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

REPAIRED_SHA = "dfa9473bcc0bb798e117f7f42461dded291cfa9f80e6f173fc1b6baedd6508fb"
SOURCE_SHA = "36425af2ebabccf2f6b1a14b49d5ed7a253441ac4956f34ca931b1e4064f9969"
SCANS = [
    (
        "BSA1_MS1_spectrum_1011.csv",
        "223f2dccd07d6598c4a89b3b1c31ae075318f076ca764b4e0fa90f0a51ac2bbc",
        467,
        1501.41394042969,
    ),
    (
        "BSA1_MS1_spectrum_1012.csv",
        "cc13f2d9a83737e3f6375c3b2d86c30520e4ce453eb61e6d5d299c8e124844da",
        478,
        1503.03125,
    ),
    (
        "BSA1_MS2_spectrum_2442.csv",
        "c003211019f25d73ed4993bbedcf1619f4c3ce567ff27302e4a0598dc21b1fb7",
        102,
        1503.96166992188,
    ),
]
URL = "https://raw.githubusercontent.com/OpenMS/pyopenms-docs/master/src/data/BSA1.mzML"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def archive_files(path):
    """Read only known small files from this supplied fixture, never extract code."""
    result = {}
    wanted = {s[0] for s in SCANS} | {
        "BSA1_repaired.mzML",
        "BSA1_scan_summary_for_learning.csv",
    }
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            name = Path(entry.filename).name
            if name not in wanted:
                continue
            if name in result or entry.file_size > 16 * 1024 * 1024:
                raise ValueError("Duplicate or oversized BSA fixture member")
            with archive.open(entry) as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("BSA fixture exceeds bounds")
            result[name] = raw
    if set(result) != wanted:
        raise ValueError("Missing BSA fixture files")
    return result


def verify_repair(raw):
    if sha(raw) != REPAIRED_SHA:
        raise ValueError("Repaired fixture differs from the reviewed supplied file")
    pointer = int(re.search(rb"<indexListOffset>(\d+)</indexListOffset>", raw)[1])
    assert raw[pointer:].startswith(b"<indexList ")
    checksum = re.search(rb"<fileChecksum>([0-9a-f]+)</fileChecksum>", raw)
    # HUPO-PSI indexed mzML: hash through the opening fileChecksum tag.
    assert hashlib.sha1(raw[: checksum.start(1)]).hexdigest() == checksum[1].decode()
    offsets = re.findall(rb'<offset idRef="([^"]+)">(\d+)</offset>', raw)
    assert len(offsets) == 1684
    for identifier, value in offsets:
        start = int(value)
        assert raw[start:].startswith(b"<spectrum ")
        assert b'id="' + identifier + b'"' in raw[start : raw.index(b">", start) + 1]
    original = raw.replace(
        b"<indexListOffset>13524736</indexListOffset>",
        b"<indexListOffset>13524735</indexListOffset>",
    )
    original = re.sub(
        rb"<fileChecksum>[0-9a-f]+</fileChecksum>",
        b"<fileChecksum>0</fileChecksum>",
        original,
    )
    assert sha(original) == SOURCE_SHA
    end = raw.index(b"</mzML>") + len(b"</mzML>")
    assert raw[:end] == original[:end]
    return {
        "repaired_sha256": sha(raw),
        "source_sha256_reconstructed": sha(original),
        "indexed_sha1": checksum[1].decode(),
        "offsets_checked": len(offsets),
        "mzml_document_preserved": True,
        "acquisition_groups": 1,
    }


def run(archive, output, *, pdf=False):
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.gui.services.study_service import StudyService
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from virtual_lab.pilots.datasets import MSDatasetService
    from virtual_lab.pilots.lease import WorkspaceLease
    from virtual_lab.pilots.ms_workflow import load_manifest, normalize_centroid_csv
    from virtual_lab.pilots.reporting import verify_report_files
    from virtual_lab.pilots.schemas import PilotError

    files = archive_files(archive)
    result = {
        "repair": verify_repair(files["BSA1_repaired.mzML"]),
        "datasets": [],
        "scope": "Software workflow only; one acquisition; evidence UNKNOWN; no INTENT training",
        "source_url": URL,
        "archive_sha256": sha(Path(archive).read_bytes()),
    }
    try:
        normalize_centroid_csv(files["BSA1_scan_summary_for_learning.csv"])
    except PilotError:
        result["scan_summary_rejected"] = True
    else:
        raise AssertionError("Scan summary was accepted as a spectrum")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    workspace = output / "workspace"
    workspace.mkdir()
    with WorkspaceLease(workspace) as lease:
        ledger = GenesisLedger(str(workspace / "genesis.db"))
        store = ExperimentStore(str(workspace / "experiments.db"))
        try:
            study = StudyService(WorkspaceState(), ledger, store)
            project = study.create_project("BSA public-reference workflow verification")
            experiment = study.create_experiment(
                project,
                "BSA1: three scans, one acquisition",
                "Are preserved spectral values reproducible and traceable?",
            )
            service = MSDatasetService(
                ledger, store, workspace / "ms-pilot-runs", lease=lease
            )
            source_dir = output / "sources"
            source_dir.mkdir()
            for name, expected, count, seconds in SCANS:
                assert sha(files[name]) == expected
                source = source_dir / name
                source.write_bytes(files[name])
                observation = service.import_csv(
                    source,
                    experiment_id=experiment,
                    pilot_id="bsa-reference-workflow",
                    dataset_id=source.stem,
                    sample_id="BSA1-single-acquisition",
                    instrument_id="claimed-LTQ-Orbitrap-XL",
                    operator_id="software-workflow-check",
                    acquired_at=None,
                    mz_units="m/z",
                    intensity_units=None,
                    data_origin="public_reference",
                    approved_nonconfidential=True,
                    source_reference={
                        "accession": "OpenMS-BSA1/" + source.stem,
                        "url": URL,
                        "license": "Dataset redistribution terms not established; local user-supplied evaluation only",
                        "attribution": "OpenMS / pyOpenMS example; user-supplied repaired derivative",
                        "notes": f"All three scans share acquisition group BSA1-single-acquisition. Relative scan time {seconds} seconds is not an acquisition UTC timestamp. Exact decoded spectral values; origin/accuracy unverified.",
                    },
                )
                run_id = observation.session_id
                manifest = load_manifest(service.manifest_path(run_id))
                assert (
                    manifest["source_sha256"] == expected
                    and manifest["peak_count"] == count
                )
                assert (
                    observation.epistemic_state.value == "UNKNOWN"
                    and manifest["acquired_at_utc"] is None
                )
                assert service.reprocess(run_id)["identical"]
                assert service.test_alteration(run_id)["detected"]
                service.review(
                    run_id,
                    reviewer="software-workflow-reviewer",
                    approved=True,
                    note="Byte preservation, rerun, traceability and isolated alteration checks passed. Not a scientific or training approval.",
                )
                target = output / (
                    source.stem + "-workflow-report" + (".pdf" if pdf else ".json")
                )
                service.export_report(run_id, target)
                assert verify_report_files(target.with_suffix(".sha256"))["verified"]
                report = json.loads(target.with_suffix(".json").read_bytes())
                assert report["workflow_check_status"] == "PASS"
                result["datasets"].append(
                    {
                        "name": name,
                        "peaks": count,
                        "source_sha256": expected,
                        "run_id": run_id,
                        "manifest_sha256": report["manifest_sha256"],
                        "experiment_id": experiment,
                        "group_id": "BSA1-single-acquisition",
                        "report": target.name,
                        "checks": report["acceptance_checks"],
                    }
                )
                (output / (source.stem + "-export-receipt.json")).write_text(
                    json.dumps(service.events(run_id)[-1], indent=2) + "\n"
                )
            assert len(store.get_observations_for_experiment(experiment)) == 3
            assert not list(
                ledger.conn.execute(
                    "SELECT 1 FROM ledger_events WHERE event_type LIKE 'INTENT_%'"
                )
            )
            study.export_study(output / "BSA-three-scans-one-acquisition.vlab-study")
            ledger.verify_chain()
        finally:
            store.close()
            ledger.conn.close()
    (output / "verification-results.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.archive, args.output, pdf=args.pdf), indent=2))
