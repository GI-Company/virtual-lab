"""Bounded, deterministic intake for approved nonconfidential centroid peak lists."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from pydantic import ValidationError
from virtual_lab.version import __version__
from virtual_lab.pilots.schemas import (AcquisitionMetadata, Manifest, PilotError,
    MAX_SOURCE_BYTES, MAX_PEAKS, MAX_MANIFEST_BYTES, PROCESSING_VERSION)
from virtual_lab.pilots.storage import checked_path, read_bounded, write_private

SCHEMA_VERSION = 2
FIELDS = ('mz', 'intensity')
NUMBER = re.compile(r'^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$')
LIMITATIONS = [
    'No identity, purity, fragmentation, calibration, or protein structural claims',
    'Checksums alone do not authenticate instrument origin or scientific validity',
    'Imported evidence remains UNKNOWN, including after workflow approval',
    'Exact decimal normalization sorts by m/z then intensity; duplicates are preserved',
]


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _decimal(value, line):
    if len(value) > 128 or not NUMBER.fullmatch(value):
        raise PilotError('INVALID_NUMBER', f'CSV row {line} contains an invalid numeric value')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise PilotError('INVALID_NUMBER', f'CSV row {line} contains an invalid numeric value') from exc
    # Bound decimal expansion, plotting range and aggregate memory use explicitly.
    if not result.is_finite() or (result and not -100 <= result.adjusted() <= 100):
        raise PilotError('NUMERIC_RANGE', f'CSV row {line} exceeds supported numeric range (1e-100 to <1e101)')
    digits = ''.join(str(d) for d in result.as_tuple().digits).rstrip('0')
    if len(digits) > 100:
        raise PilotError('NUMERIC_PRECISION', f'CSV row {line} exceeds 100 significant digits')
    return result


def canonical_decimal(value):
    if value == 0:
        return '0'
    text = format(value, 'f')
    fixed = text.rstrip('0').rstrip('.') if '.' in text else text
    if len(fixed) <= 128:
        return fixed
    digits = ''.join(str(d) for d in value.as_tuple().digits).rstrip('0')
    mantissa = digits[0] + ('.' + digits[1:] if len(digits) > 1 else '')
    return ('-' if value < 0 else '') + mantissa + 'e' + str(value.adjusted())


def parse_centroids(source):
    if not source or len(source) > MAX_SOURCE_BYTES:
        raise PilotError('SIZE_LIMIT', 'CSV must be nonempty and at most 16 MiB')
    try:
        text = source.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise PilotError('ENCODING', 'CSV must be UTF-8 encoded') from exc
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    peaks = []
    try:
        if next(reader, None) != list(FIELDS):
            raise PilotError('HEADER', 'CSV header must be exactly: mz,intensity')
        for row in reader:
            if len(peaks) >= MAX_PEAKS:
                raise PilotError('ROW_LIMIT', f'CSV exceeds {MAX_PEAKS} peak rows')
            if len(row) != 2:
                raise PilotError('ROW_SCHEMA', f'CSV row {reader.line_num} must contain exactly two values')
            mz, intensity = (_decimal(v, reader.line_num) for v in row)
            if mz <= 0 or intensity < 0:
                raise PilotError('NUMERIC_RANGE', f'CSV row {reader.line_num} requires mz > 0 and intensity >= 0')
            peaks.append((mz, intensity))
    except csv.Error as exc:
        raise PilotError('MALFORMED_CSV', 'Malformed CSV syntax or oversized field') from exc
    if not peaks:
        raise PilotError('NO_PEAKS', 'CSV must contain at least one peak')
    return peaks


def normalize_centroid_csv(source):
    peaks = parse_centroids(source)
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(FIELDS)
    for mz, intensity in sorted(peaks):
        writer.writerow((canonical_decimal(mz), canonical_decimal(intensity)))
    return output.getvalue().encode('utf-8'), len(peaks)


def _parse_manifest(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    try:
        parsed = Manifest.model_validate(json.loads(raw, object_pairs_hook=unique))
        manifest = parsed.model_dump()
        for entry in manifest['artifacts']:
            expected = manifest['source_sha256' if entry['file'] == 'source.csv' else 'normalized_sha256']
            if expected != entry['sha256']:
                raise ValueError('Conflicting artifact hashes')
        return manifest
    except (ValidationError, ValueError, UnicodeError) as exc:
        if isinstance(exc, PilotError):
            raise
        raise PilotError('MANIFEST_SCHEMA', 'Invalid manifest schema; expected exactly source.csv and peaks.csv with consistent metadata') from exc


def load_manifest(manifest_path):
    path = Path(manifest_path)
    if path.name != 'manifest.json':
        raise PilotError('MANIFEST_SCHEMA', 'Expected a regular manifest.json file')
    return _parse_manifest(read_bounded(path, MAX_MANIFEST_BYTES))


def import_centroid_csv(input_path, output_root, *, sample_id, instrument_id, operator_id,
                        approved_nonconfidential, acquired_at=None,
                        pilot_id='mild-biotec-initial-ms', dataset_id=None,
                        mz_units=None, intensity_units=None, expected_source_sha256=None):
    if approved_nonconfidential is not True:
        raise PilotError('DATA_APPROVAL', 'Explicit approval for nonconfidential pilot data is required')
    run_id = str(uuid.uuid4())
    try:
        metadata = AcquisitionMetadata(pilot_id=pilot_id, dataset_id=dataset_id or run_id,
            sample_id=sample_id, instrument_id=instrument_id, operator_id=operator_id,
            acquired_at_utc=acquired_at, mz_units=mz_units, intensity_units=intensity_units)
    except ValidationError as exc:
        raise PilotError('METADATA', str(exc)) from exc
    raw = read_bounded(input_path, MAX_SOURCE_BYTES)
    if expected_source_sha256 and _sha256(raw) != expected_source_sha256:
        raise PilotError('SOURCE_CHANGED', 'Source differs from the validated preview; validate it again')
    normalized, count = normalize_centroid_csv(raw)
    out = checked_path(output_root)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    duplicate_of = []
    # Only complete valid runs count as previous imports. Never silently discard duplicates.
    for previous in out.glob('*/manifest.json'):
        old = load_manifest(previous)
        if old['source_sha256'] == _sha256(raw):
            duplicate_of.append(old['run_id'])
    warnings = ['Instrument origin, calibration and scientific validity are unverified']
    if mz_units is None or intensity_units is None:
        warnings.append('Unspecified units have been preserved as null')
    if duplicate_of:
        warnings.append('Identical source bytes were previously imported; this is a separate run')
    manifest = Manifest(schema_version=2, **metadata.model_dump(), run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(), source_filename=Path(input_path).name,
        data_kind='centroid_peak_list', epistemic_state='UNKNOWN', import_status='accepted',
        input_format='strict_csv_mz_intensity_v1', processing_version=PROCESSING_VERSION,
        software_version=__version__, peak_count=count, source_sha256=_sha256(raw),
        normalized_sha256=_sha256(normalized), approved_nonconfidential=True,
        duplicate_of=duplicate_of, warnings=warnings, limitations=LIMITATIONS,
        artifacts=[{'file': name, 'sha256': _sha256(content), 'size_bytes': len(content)}
                   for name, content in [('source.csv', raw), ('peaks.csv', normalized)]]).model_dump()
    temp = Path(tempfile.mkdtemp(prefix='.ms-intake-', dir=out))
    try:
        write_private(temp / 'source.csv', raw)
        write_private(temp / 'peaks.csv', normalized)
        write_private(temp / 'manifest.json', json_bytes(manifest))
        verify_centroid_bundle(temp / 'manifest.json')
        final = out / run_id
        temp.rename(final)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return final / 'manifest.json'


def read_verified_bundle(manifest_path, *, expected_manifest_sha256=None):
    path = Path(manifest_path)
    if path.name != 'manifest.json':
        raise PilotError('MANIFEST_SCHEMA', 'Expected a regular manifest.json file')
    manifest_raw = read_bounded(path, MAX_MANIFEST_BYTES)
    if expected_manifest_sha256 and _sha256(manifest_raw) != expected_manifest_sha256:
        raise PilotError('MANIFEST_INTEGRITY', 'Manifest differs from the independently recorded digest')
    manifest = _parse_manifest(manifest_raw)
    contents = {}
    for entry in manifest['artifacts']:
        payload = read_bounded(path.parent / entry['file'], MAX_SOURCE_BYTES * (1 if entry['file'] == 'source.csv' else 4))
        if len(payload) != entry['size_bytes'] or _sha256(payload) != entry['sha256']:
            raise PilotError('ARTIFACT_INTEGRITY', f"Artifact integrity mismatch: {entry['file']}")
        contents[entry['file']] = payload
    normalized, count = normalize_centroid_csv(contents['source.csv'])
    if normalized != contents['peaks.csv'] or count != manifest['peak_count']:
        raise PilotError('NORMALIZATION_MISMATCH', 'Peak normalization or peak count mismatch')
    contents['manifest.json'] = manifest_raw
    return manifest, contents, _sha256(manifest_raw)


def verify_centroid_bundle(manifest_path, *, expected_manifest_sha256=None):
    manifest, _, _ = read_verified_bundle(manifest_path, expected_manifest_sha256=expected_manifest_sha256)
    return {'verified': True, 'run_id': manifest['run_id'], 'peak_count': manifest['peak_count'],
            'epistemic_state': 'UNKNOWN', 'note': 'File integrity only; instrument origin and scientific validity are unverified'}


def main():
    parser = argparse.ArgumentParser(description='Nonconfidential MS centroid pilot intake')
    commands = parser.add_subparsers(dest='command', required=True)
    ingest = commands.add_parser('import')
    ingest.add_argument('input', type=Path)
    ingest.add_argument('--output-root', type=Path, required=True)
    for field in ('sample-id', 'instrument-id', 'operator-id'):
        ingest.add_argument('--' + field, required=True)
    for field in ('pilot-id', 'dataset-id', 'acquired-at', 'mz-units', 'intensity-units'):
        ingest.add_argument('--' + field)
    ingest.add_argument('--approved-nonconfidential', action='store_true')
    verify = commands.add_parser('verify')
    verify.add_argument('manifest', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'import':
            fields = vars(args).copy()
            for key in ('command', 'input', 'output_root'):
                fields.pop(key)
            if fields['pilot_id'] is None:
                fields.pop('pilot_id')
            path = import_centroid_csv(args.input, args.output_root, **fields)
            result = {'manifest': str(path), **verify_centroid_bundle(path)}
        else:
            result = verify_centroid_bundle(args.manifest)
    except (PilotError, OSError) as exc:
        print(json.dumps({'status': 'rejected', 'code': getattr(exc, 'code', 'STORAGE_FAILURE'), 'message': str(exc)}))
        raise SystemExit(2)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
