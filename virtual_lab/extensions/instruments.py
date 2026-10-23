"""Vendor-neutral file acquisition contract; hardware adapters can implement the protocol.

Imported vendor files retain UNKNOWN epistemic status. Byte hashes authenticate
neither the instrument nor the scientific interpretation. There is no actuation
path in this adapter.
"""
import csv
import hashlib
import io
import math
from pathlib import Path
from typing import Protocol, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from virtual_lab.core.canonical import canonical_json, strict_json_loads


class Channel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    column: str = Field(min_length=1, max_length=100)
    quantity: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=80)
    role: Literal['axis', 'signal']


class InstrumentManifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format: Literal['vlab-instrument-v1']
    instrument_id: str = Field(min_length=1, max_length=100)
    manufacturer: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    acquisition_id: str = Field(min_length=1, max_length=100)
    sample_id: str = Field(min_length=1, max_length=100)
    method: str = Field(min_length=1, max_length=200)
    channels: list[Channel] = Field(min_length=1, max_length=64)
    limitations: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def check_units(self):
        from virtual_lab.matter.units import ureg
        if len({c.column for c in self.channels}) != len(self.channels):
            raise ValueError('Duplicate instrument columns.')
        for channel in self.channels:
            ureg.Unit(channel.unit)
        if not any(c.role == 'signal' for c in self.channels):
            raise ValueError('Declare at least one signal channel.')
        return self


class InstrumentAdapter(Protocol):
    def describe(self) -> InstrumentManifest: ...
    def acquire(self, source: Path) -> dict: ...


class CSVInstrument:
    def __init__(self, manifest_path):
        from .models import read_manifest
        self.raw_manifest, value = read_manifest(manifest_path)
        self.manifest = InstrumentManifest.model_validate(value)

    def describe(self): return self.manifest

    def acquire(self, source):
        with Path(source).open('rb') as stream: raw = stream.read(1024*1024+1)
        if len(raw) > 1024*1024: raise ValueError('Instrument CSV exceeds 1 MiB.')
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        expected = [c.column for c in self.manifest.channels]
        if reader.fieldnames != expected: raise ValueError('CSV header must match the declared channel order exactly.')
        rows = []
        for index, row in enumerate(reader):
            if index >= 10000: raise ValueError('Instrument CSV exceeds 10000 rows.')
            if None in row or any(value is None for value in row.values()): raise ValueError('Malformed CSV row.')
            values = {name: float(value) for name, value in row.items()}
            if not all(math.isfinite(v) for v in values.values()): raise ValueError('Nonfinite instrument sample.')
            rows.append(values)
        if not rows: raise ValueError('No instrument samples.')
        return {'kind': 'instrument_import', 'epistemic_state': 'UNKNOWN',
            'declarations': self.manifest.model_dump(), 'samples': rows,
            'source_sha256': hashlib.sha256(raw).hexdigest(),
            'manifest_sha256': hashlib.sha256(self.raw_manifest).hexdigest(),
            'raw_csv_base64': __import__('base64').b64encode(raw).decode('ascii'), 'raw_manifest': self.raw_manifest.decode('utf-8'),
            'limitations': ['File import; instrument/sample identity is operator-declared.',
                'No authenticated physical acquisition or instrument control was performed.']}


def save_extension_run(result, root, ledger):
    """Store actual output bytes and anchor their hash; no invented success events."""
    import uuid
    from datetime import datetime, timezone
    from virtual_lab.core.ledger import Actor
    record = dict(result, run_id=str(uuid.uuid4()), recorded_at=datetime.now(timezone.utc).isoformat(),
                  format='vlab-extension-result-v1')
    raw = canonical_json(record); digest = hashlib.sha256(raw).hexdigest()
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    path = root / (digest + '.json')
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); __import__('os').fsync(stream.fileno())
    ledger.append('EXT_' + record['run_id'], Actor(type='USER', id='local-operator'),
        'EXTENSION_RUN_RECORDED', {'run_id': record['run_id'], 'sha256': digest,
        'file': path.name, 'kind': record['kind'], 'epistemic_state': record['epistemic_state']})
    return path
