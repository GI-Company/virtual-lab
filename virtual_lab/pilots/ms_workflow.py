"""Conservative MS centroid-list intake for nonconfidential workflow pilots.

This module validates an interchange CSV and hashes its bytes. It does NOT
identify proteins, calibrate instruments, interpret MS/MS, or establish the
origin or scientific validity of the submitted measurements.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import uuid

MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_PEAKS = 100_000
SCHEMA_VERSION = 1
FIELDS = ("mz", "intensity")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field} must use 1–80 letters, digits, dots, underscores or hyphens")
    return value


def _timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("acquired_at must be an ISO 8601 timestamp with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("acquired_at requires timezone information")
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_centroid_csv(source: bytes) -> tuple[bytes, int]:
    """Parse exact mz,intensity CSV fields and emit deterministic sorted peaks.

    Duplicate m/z values are preserved because they may represent distinct
    centroids. No peak filtering, recalibration or intensity normalization occurs.
    """
    if not source or len(source) > MAX_SOURCE_BYTES:
        raise ValueError("CSV must be nonempty and at most 16 MiB")
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if reader.fieldnames is None or tuple(reader.fieldnames) != FIELDS:
        raise ValueError("CSV header must be exactly: mz,intensity")
    peaks: list[tuple[float, float]] = []
    try:
        for line, row in enumerate(reader, start=2):
            if len(peaks) >= MAX_PEAKS:
                raise ValueError(f"CSV exceeds {MAX_PEAKS} peak rows")
            if None in row or any(row[field] is None for field in FIELDS):
                raise ValueError(f"CSV row {line} must contain exactly two values")
            try:
                mz = float(row["mz"])
                intensity = float(row["intensity"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"CSV row {line} has nonnumeric values") from exc
            if not (math.isfinite(mz) and mz > 0 and math.isfinite(intensity) and intensity >= 0):
                raise ValueError(f"CSV row {line} requires finite mz > 0 and intensity >= 0")
            peaks.append((mz, intensity))
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV: {exc}") from exc
    if not peaks:
        raise ValueError("CSV must contain at least one peak")
    writer_buf = io.StringIO(newline="")
    writer = csv.writer(writer_buf, lineterminator="\n")
    writer.writerow(FIELDS)
    for mz, intensity in sorted(peaks):
        writer.writerow((format(mz, ".17g"), format(intensity, ".17g")))
    return writer_buf.getvalue().encode("utf-8"), len(peaks)


def import_centroid_csv(
    input_path: Path | str,
    output_root: Path | str,
    *,
    sample_id: str,
    instrument_id: str,
    operator_id: str,
    approved_nonconfidential: bool,
    acquired_at: str | None = None,
) -> Path:
    """Create an immutable-on-success intake directory with a hash manifest.

    Caller must confirm that the source is approved for this nonconfidential
    pilot. No network transmission or research inference is performed.
    """
    if approved_nonconfidential is not True:
        raise ValueError("Explicit approval for nonconfidential pilot data is required")
    sample_id = _identifier(sample_id, "sample_id")
    instrument_id = _identifier(instrument_id, "instrument_id")
    operator_id = _identifier(operator_id, "operator_id")
    acquisition = _timestamp(acquired_at)
    input_path = Path(input_path)
    if input_path.is_symlink() or not input_path.is_file():
        raise ValueError("Input must be a regular non-symlink CSV file")
    if input_path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("CSV exceeds 16 MiB")
    raw = input_path.read_bytes()
    normalized, peak_count = normalize_centroid_csv(raw)
    out = Path(output_root)
    out.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    temp = Path(tempfile.mkdtemp(prefix=".ms-intake-", dir=out))
    final = out / run_id
    try:
        (temp / "source.csv").write_bytes(raw)
        (temp / "peaks.csv").write_bytes(normalized)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "sample_id": sample_id,
            "instrument_id": instrument_id,
            "operator_id": operator_id,
            "acquired_at_utc": acquisition,
            "data_kind": "centroid_peak_list",
            "epistemic_state": "UNKNOWN",
            "epistemic_note": "Imported file provenance not independently established; centroid values may be processed instrument outputs.",
            "input_format": "strict_csv_mz_intensity_v1",
            "peak_count": peak_count,
            "units": {"mz": "m/z", "intensity": "source units (unverified)"},
            "artifacts": [
                {"file": "source.csv", "sha256": _sha256(raw), "size_bytes": len(raw)},
                {"file": "peaks.csv", "sha256": _sha256(normalized), "size_bytes": len(normalized)},
            ],
            "limitations": [
                "No identity, purity, fragmentation, calibration, or protein structural claims",
                "Hashes detect changes relative to this manifest but are not digital signatures",
                "Scientific provenance and permitted data use require independent review",
            ],
        }
        (temp / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        temp.rename(final)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return final / "manifest.json"


def verify_centroid_bundle(manifest_path: Path | str) -> dict:
    """Verify artifacts against manifest hashes; never certify measurement origin."""
    manifest_path = Path(manifest_path)
    if manifest_path.is_symlink() or manifest_path.name != "manifest.json":
        raise ValueError("Expected a regular manifest.json file")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("data_kind") != "centroid_peak_list":
        raise ValueError("Unsupported MS intake bundle version or data kind")
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or {e.get("file") for e in entries if isinstance(e, dict)} != {"source.csv", "peaks.csv"} or len(entries) != 2:
        raise ValueError("Manifest must contain exactly source.csv and peaks.csv")
    contents: dict[str, bytes] = {}
    for entry in entries:
        path = manifest_path.parent / entry["file"]
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or linked artifact")
        contents[entry["file"]] = payload = path.read_bytes()
        if len(payload) != entry["size_bytes"] or _sha256(payload) != entry["sha256"]:
            raise ValueError(f"Artifact integrity mismatch: {entry['file']}")
    normalized, count = normalize_centroid_csv(contents["source.csv"])
    if normalized != contents["peaks.csv"] or count != manifest.get("peak_count"):
        raise ValueError("Peak normalization or peak count mismatch")
    return {"verified": True, "run_id": manifest["run_id"], "peak_count": count,
            "epistemic_state": manifest.get("epistemic_state", "UNKNOWN"),
            "note": "File integrity only; instrument origin and scientific validity are unverified"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Nonconfidential MS centroid pilot intake")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("import", help="Import strict mz,intensity CSV")
    ingest.add_argument("input", type=Path)
    ingest.add_argument("--output-root", type=Path, required=True)
    ingest.add_argument("--sample-id", required=True)
    ingest.add_argument("--instrument-id", required=True)
    ingest.add_argument("--operator-id", required=True)
    ingest.add_argument("--acquired-at")
    ingest.add_argument("--approved-nonconfidential", action="store_true")
    verify = commands.add_parser("verify", help="Verify intake bundle file integrity")
    verify.add_argument("manifest", type=Path)
    args = parser.parse_args()
    if args.command == "import":
        manifest = import_centroid_csv(
            args.input, args.output_root, sample_id=args.sample_id,
            instrument_id=args.instrument_id, operator_id=args.operator_id,
            acquired_at=args.acquired_at, approved_nonconfidential=args.approved_nonconfidential,
        )
        result = {"manifest": str(manifest), **verify_centroid_bundle(manifest)}
    else:
        result = verify_centroid_bundle(args.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
