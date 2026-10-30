"""Adversarial and round-trip tests for nonconfidential MS pilot intake."""
import json
from pathlib import Path

import pytest

from virtual_lab.pilots.ms_workflow import (
    import_centroid_csv,
    normalize_centroid_csv,
    verify_centroid_bundle,
)


def test_parse_deterministic_and_preserve_duplicate_centroids():
    data, count = normalize_centroid_csv(b"mz,intensity\n202.1,7\n101.5,0\n101.5,3\n")
    assert count == 3
    assert data.decode().splitlines()[:3] == ["mz,intensity", "101.5,0", "101.5,3"]
    assert normalize_centroid_csv(data)[0] == data


@pytest.mark.parametrize("csv_data", [
    b"", b"a,b\n1,2\n", b"mz,intensity\n", b"mz,intensity\n0,1\n",
    b"mz,intensity\n-1,1\n", b"mz,intensity\n1,-1\n", b"mz,intensity\nnan,2\n",
    b"mz,intensity\n1,inf\n", b"mz,intensity\n1,2,3\n", b"mz,intensity\nx,2\n",
])
def test_bad_peak_data_rejected(csv_data):
    with pytest.raises(ValueError):
        normalize_centroid_csv(csv_data)


def test_import_requires_explicit_data_approval(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("mz,intensity\n100,50\n")
    with pytest.raises(ValueError, match="approval"):
        import_centroid_csv(source, tmp_path / "out", sample_id="s1",
                            instrument_id="ms1", operator_id="op1", approved_nonconfidential=False)
    assert not (tmp_path / "out").exists()


def test_round_trip_and_tamper_detection(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("mz,intensity\n101.5,30\n100.0,11\n")
    manifest_path = import_centroid_csv(
        source, tmp_path / "out", sample_id="sample-1",
        instrument_id="instrument-1", operator_id="analyst-1",
        acquired_at="2026-10-29T18:00:00-04:00",
        approved_nonconfidential=True,
    )
    verified = verify_centroid_bundle(manifest_path)
    assert verified["peak_count"] == 2
    assert verified["epistemic_state"] == "UNKNOWN"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["acquired_at_utc"] == "2026-10-29T22:00:00+00:00"
    assert manifest["artifacts"][0]["file"] == "source.csv"
    assert "No identity" in manifest["limitations"][0]
    (manifest_path.parent / "source.csv").write_text("mz,intensity\n101.5,29\n100.0,11\n")
    with pytest.raises(ValueError, match="integrity"):
        verify_centroid_bundle(manifest_path)


def test_metadata_and_invalid_timezone_rejected(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("mz,intensity\n100,1\n")
    for sample_id, acquired_at in (("../bad", None), ("valid", "2026-10-29T12:30:00")):
        with pytest.raises(ValueError):
            import_centroid_csv(source, tmp_path / "out", sample_id=sample_id,
                                instrument_id="instrument", operator_id="operator",
                                acquired_at=acquired_at, approved_nonconfidential=True)


def test_manifest_rejects_added_artifact(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("mz,intensity\n100,1\n")
    manifest_path = import_centroid_csv(source, tmp_path / "out", sample_id="s1",
                                        instrument_id="ms1", operator_id="op1",
                                        approved_nonconfidential=True)
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"].append({"file": "../secret", "sha256": "0", "size_bytes": 0})
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="exactly"):
        verify_centroid_bundle(manifest_path)
