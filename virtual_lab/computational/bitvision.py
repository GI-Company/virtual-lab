"""Read-only BitVision simulator-evaluation audit. No checkpoint deserialization or inference."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from statistics import mean, median
import zipfile

from .artifacts import digest, write_json

EXPECTED_INPUTS = {'x': (1, ('batch', 256, 10)),
                   'mask': (9, ('batch', 256)),
                   'ctx': (1, ('batch', 18))}
EXPECTED_OUTPUTS = {'focus_logits': (1, ('batch', 256)),
                    'action_mean': (1, ('batch', 6)),
                    'action_std': (1, ('batch', 6)),
                    'value': (1, ('batch',))}
REQUIRED_MEMBERS = {'episode_results.json', 'summary.csv', 'paired_deltas.csv', 'action_diagnostics.json'}


def _path(value: str, max_bytes: int) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('Choose an existing regular file by absolute path.')
    if path.stat().st_size > max_bytes:
        raise ValueError('A supplied file exceeds the audit size limit.')
    return path


def _varint(data: memoryview, pos: int):
    result = shift = 0
    for _ in range(10):
        if pos >= len(data):
            raise ValueError('Truncated ONNX protobuf.')
        byte = data[pos]; pos += 1
        result |= (byte & 127) << shift
        if byte < 128:
            return result, pos
        shift += 7
    raise ValueError('Invalid ONNX varint.')


def _fields(data: memoryview):
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        field, wire = tag >> 3, tag & 7
        if field == 0:
            raise ValueError('Invalid ONNX field.')
        if wire == 0:
            value, pos = _varint(data, pos)
        elif wire == 2:
            length, pos = _varint(data, pos)
            if length > len(data) - pos:
                raise ValueError('Truncated ONNX field.')
            value = data[pos:pos + length]; pos += length
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            if len(data) - pos < length:
                raise ValueError('Truncated ONNX field.')
            value = data[pos:pos + length]; pos += length
        else:
            raise ValueError('Unsupported ONNX wire type.')
        yield field, value


def _get(data: memoryview, field: int):
    return [value for number, value in _fields(data) if number == field]


def _text(data: memoryview):
    return bytes(data).decode('utf-8')


def _value_info(data: memoryview):
    name = _text(_get(data, 1)[0])
    tensor = _get(_get(data, 2)[0], 1)[0]
    dtype = _get(tensor, 1)[0]
    shape = _get(tensor, 2)
    dimensions = []
    if shape:
        for dim in _get(shape[0], 1):
            number, symbol = _get(dim, 1), _get(dim, 2)
            dimensions.append(number[0] if number else _text(symbol[0]) if symbol else None)
    return name, (dtype, tuple(dimensions))


def onnx_signature(path: Path) -> dict:
    """Read protobuf graph signature only; this is not a full ONNX semantic checker."""
    model = memoryview(path.read_bytes())
    graph = _get(model, 7)[0]
    inputs = dict(_value_info(value) for value in _get(graph, 11))
    outputs = dict(_value_info(value) for value in _get(graph, 12))
    if inputs != EXPECTED_INPUTS or set(outputs) != set(EXPECTED_OUTPUTS):
        raise ValueError('ONNX model does not have the expected BitVision interface.')
    for name, (dtype, dimensions) in outputs.items():
        expected_dtype, expected_dimensions = EXPECTED_OUTPUTS[name]
        if dtype != expected_dtype or len(dimensions) != len(expected_dimensions):
            raise ValueError('ONNX output type or rank differs from BitVision interface.')
        if any(actual != expected for actual, expected in zip(dimensions, expected_dimensions)
               if isinstance(actual, int) or expected == 'batch'):
            raise ValueError('ONNX output dimensions differ from BitVision interface.')
    opsets = _get(model, 8)
    versions = [_get(value, 2)[0] for value in opsets if _get(value, 2)]
    if not versions or max(versions) < 18:
        raise ValueError('Expected an ONNX opset 18 or newer model.')
    initializer_types = Counter(_get(value, 2)[0] for value in _get(graph, 5))
    return {'sha256': digest(path), 'bytes': path.stat().st_size,
            'inputs': {name: {'dtype': dtype, 'shape': list(shape)} for name, (dtype, shape) in inputs.items()},
            'outputs': {name: {'dtype': dtype, 'shape': list(shape)} for name, (dtype, shape) in outputs.items()},
            'opset_versions': versions, 'initializer_types': dict(initializer_types),
            'verification_scope': 'Static graph signature only; weights and runtime outputs were not executed.'}


def _finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Nonfinite episode metric.')
    return number


def _json(raw):
    return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON value.')))


def _read_member(bundle, name):
    item = bundle.getinfo(name)
    if item.file_size > 10_000_000:
        raise ValueError('Audit metadata member exceeds 10 MB.')
    return bundle.read(item)


def audit_archive(path: Path) -> dict:
    with zipfile.ZipFile(path) as bundle:
        members = bundle.infolist()
        names = [item.filename for item in members]
        if len(names) != len(set(names)) or len(names) > 100 or sum(item.file_size for item in members) > 250_000_000:
            raise ValueError('Archive inventory or size limit failed.')
        if not REQUIRED_MEMBERS.issubset(names):
            raise ValueError('Archive lacks episode results or diagnostic tables.')
        payload = _json(_read_member(bundle, 'episode_results.json'))
        summary = list(csv.DictReader(io.StringIO(_read_member(bundle, 'summary.csv').decode('utf-8'))))
        deltas = list(csv.DictReader(io.StringIO(_read_member(bundle, 'paired_deltas.csv').decode('utf-8'))))
        action_diagnostics = _json(_read_member(bundle, 'action_diagnostics.json'))
        has_checkpoint = 'checkpoint_000500.pt' in names
    records = payload['records']
    if not isinstance(records, list) or not records or len(records) > 100_000:
        raise ValueError('Invalid episode records.')
    grouped = defaultdict(dict)
    for record in records:
        key = tuple(record[name] for name in ('split', 'accession', 'regime', 'seed'))
        variant = record['variant']
        if variant not in ('checkpoint', 'untreated') or variant in grouped[key]:
            raise ValueError('Duplicate or invalid episode variant.')
        grouped[key][variant] = record
        for field in ('return', 'toxicity', 'mean_total_dose_per_step'):
            _finite(record[field])
    if any(set(pair) != {'checkpoint', 'untreated'} for pair in grouped.values()):
        raise ValueError('Episodes lack same-seed checkpoint/untreated pairs.')
    buckets = defaultdict(list)
    for (split, accession, regime, seed), pair in grouped.items():
        buckets[(split, regime)].append(pair)
    breakdown = []
    for (split, regime), pairs in sorted(buckets.items()):
        checkpoint = [pair['checkpoint'] for pair in pairs]
        untreated = [pair['untreated'] for pair in pairs]
        breakdown.append({'split': split, 'regime': regime, 'paired_seeds': len(pairs),
                          'accessions': sorted({r['accession'] for r in checkpoint}),
                          'checkpoint_eradication_rate': mean(bool(r['eradicated']) for r in checkpoint),
                          'untreated_eradication_rate': mean(bool(r['eradicated']) for r in untreated),
                          'checkpoint_failure_rate': mean(bool(r['failed']) for r in checkpoint),
                          'untreated_failure_rate': mean(bool(r['failed']) for r in untreated),
                          'checkpoint_mean_return': mean(_finite(r['return']) for r in checkpoint),
                          'untreated_mean_return': mean(_finite(r['return']) for r in untreated),
                          'checkpoint_mean_toxicity': mean(_finite(r['toxicity']) for r in checkpoint),
                          'untreated_mean_toxicity': mean(_finite(r['toxicity']) for r in untreated),
                          'checkpoint_mean_total_dose_per_step': mean(_finite(r['mean_total_dose_per_step']) for r in checkpoint),
                          'outcome_overlap_count': sum(bool(r['eradicated']) and bool(r['failed']) for r in checkpoint)})
    overlap = [r for r in records if bool(r['eradicated']) and bool(r['failed'])]
    issues = []
    if overlap:
        issues.append(f'{len(overlap)} episodes are marked both eradicated and failed; define the endpoints before interpretation.')
    if not has_checkpoint:
        issues.append('Expected checkpoint_000500.pt is absent from the archive.')
    if not summary or not deltas or not action_diagnostics:
        issues.append('One or more exported aggregate/diagnostic tables are empty.')
    # Cross-check the exported summary instead of silently trusting its labels.
    by_group = defaultdict(list)
    for record in records:
        by_group[tuple(record[key] for key in ('split', 'accession', 'regime', 'variant'))].append(record)
    for row in summary:
        key = tuple(row[name] for name in ('split', 'accession', 'regime', 'variant'))
        source = by_group.get(key)
        if not source or len(source) != int(row['episodes']):
            raise ValueError('Summary rows disagree with episode identities or counts.')
        for field, metric in (('eradication_rate', 'eradicated'), ('failure_rate', 'failed')):
            if abs(_finite(row[field]) - mean(bool(r[metric]) for r in source)) > 1e-9:
                raise ValueError(f'Summary {field} disagrees with episodes.')
        for field, metric, aggregate in (
            ('mean_return', 'return', mean), ('median_steps', 'steps', median),
            ('mean_final_healthy', 'healthy', mean), ('mean_final_infected', 'infected', mean),
            ('mean_final_toxicity', 'toxicity', mean),
            ('mean_max_resistance', 'max_resistance', mean),
            ('mean_total_dose_per_step', 'mean_total_dose_per_step', mean),
        ):
            if abs(_finite(row[field]) - aggregate(_finite(r[metric]) for r in source)) > 1e-9:
                raise ValueError(f'Summary {field} disagrees with episodes.')
    if len(summary) != len(by_group):
        raise ValueError('Summary omits episode groups.')
    expected_delta_keys = {(split, accession, regime) for split, accession, regime, _ in by_group}
    seen_deltas = set()
    for row in deltas:
        key = tuple(row[name] for name in ('split', 'accession', 'regime'))
        if key not in expected_delta_keys or key in seen_deltas:
            raise ValueError('Paired-delta identity is missing or duplicated.')
        seen_deltas.add(key)
        checkpoint, untreated = (by_group[key + (variant,)] for variant in ('checkpoint', 'untreated'))
        for field, metric in (
            ('delta_eradication_rate', 'eradicated'), ('delta_failure_rate', 'failed'),
            ('delta_return', 'return'), ('delta_final_healthy', 'healthy'),
            ('delta_final_infected', 'infected'), ('delta_toxicity', 'toxicity'),
        ):
            calculated = mean(_finite(r[metric]) for r in checkpoint) - mean(_finite(r[metric]) for r in untreated)
            if abs(_finite(row[field]) - calculated) > 1e-9:
                raise ValueError(f'Paired {field} disagrees with episodes.')
    if seen_deltas != expected_delta_keys:
        raise ValueError('Paired-delta table omits episode groups.')
    doses = [float(value) for row in action_diagnostics for value in row.get('dose_mean', [])]
    if doses and max(doses) > .9:
        issues.append('At least one action component has mean dose above 0.9 of its normalized range; inspect saturation and toxicity.')
    return {'status': 'SIMULATOR_ONLY', 'checkpoint_update': payload.get('checkpoint_update'),
            'archive_sha256': digest(path), 'archive_bytes': path.stat().st_size,
            'episode_count': len(records), 'paired_seed_count': len(grouped),
            'breakdown': breakdown, 'issues': issues,
            'tables': {'summary_rows': len(summary), 'paired_delta_rows': len(deltas),
                       'action_diagnostic_rows': len(action_diagnostics)},
            'limitations': ['Only supplied simulator outcomes were audited; no policy inference or simulator replay was performed.',
                            'Untreated is a weak comparator; no active treatment baseline is included.',
                            'Held-out protein accessions remain within the same simulator, not independent biological experiments.',
                            'The archive does not specify the feature normalization, six action meanings/units, or simulator equations.',
                            'AlphaFold reference structures in the archive do not validate cellular treatment effects.']}


class BitVisionAuditAdapter:
    def execute(self, request, directory: Path) -> dict:
        archive = _path(request.archive_path, 250_000_000)
        fp16 = _path(request.fp16_path, 64_000_000)
        fp32 = _path(request.fp32_path, 64_000_000)
        audit = audit_archive(archive)
        models = {'fp16': onnx_signature(fp16), 'fp32': onnx_signature(fp32)}
        if models['fp16']['initializer_types'] != {10: 105} or models['fp32']['initializer_types'] != {1: 105}:
            raise ValueError('ONNX parameter inventory does not match the supplied FP16/FP32 policy pair.')
        write_json(directory / 'bitvision-audit.json', {'format': 'virtuallab-bitvision-audit',
                   'schema_version': 1, 'audit': audit, 'models': models})
        return {'provider': 'Local BitVision simulator export', 'source': str(archive),
                'model_version': 'checkpoint update 500', 'epistemic_state': 'CALCULATED',
                'source_epistemic_state': 'SIMULATED',
                'summary': {'status': audit['status'], 'episode_count': audit['episode_count'],
                            'paired_seed_count': audit['paired_seed_count'], 'breakdown': audit['breakdown'],
                            'issues': audit['issues']},
                'limitations': audit['limitations']}
