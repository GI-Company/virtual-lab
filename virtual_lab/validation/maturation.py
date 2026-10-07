"""Frozen-model evaluation with explicit acquisition and timing eligibility.

Metadata eligibility is not authentication, blinding, or a biological pass/fail.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Literal
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import Field, model_validator
from virtual_lab.biology.objects import Record
from virtual_lab.biology.maturation_validation import prediction, metrics


class Context(Record):
    reporter: str = Field(min_length=1, max_length=200)
    organism: str = Field(min_length=1, max_length=200)
    strain: str = Field(min_length=1, max_length=200)
    temperature_c: float = Field(ge=0, le=100)
    assay: Literal['live_cell', 'purified_protein']


class Acquisition(Record):
    id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=500)
    date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    biological_unit_id: str | None = Field(default=None, min_length=1, max_length=200)
    source_hashes: tuple[str, ...] = Field(min_length=1, max_length=100)
    event_time_min: float | None = Field(default=None, ge=0, le=1e9)
    timing_basis: Literal['recorded', 'author_aligned', 'nominal', 'growth_proxy', 'unknown']
    timing_source: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def valid_hashes(self):
        for sha in self.source_hashes:
            if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValueError('Source hashes must be lowercase SHA256 values.')
        datetime.strptime(self.date,'%Y-%m-%d')
        return self


class FrozenModel(Record):
    format: Literal['virtuallab-frozen-maturation-model'] = 'virtuallab-frozen-maturation-model'
    schema_version: Literal[1] = 1
    label: str = Field(min_length=1, max_length=200)
    source_report_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    context: Context
    training_acquisitions: tuple[Acquisition, ...] = Field(min_length=1, max_length=100)
    maturation_per_hour: float = Field(gt=0, le=100)
    immature_to_initial_mature_ratio: float = Field(ge=0, le=10)
    valid_duration_h: float = Field(gt=0, le=168)
    synthetic: bool = False

    @model_validator(mode='after')
    def unique_training_acquisitions(self):
        if len({a.id.casefold() for a in self.training_acquisitions}) != len(self.training_acquisitions):
            raise ValueError('Training acquisition IDs must be unique.')
        return self


class Dataset(Record):
    format: Literal['virtuallab-maturation-dataset'] = 'virtuallab-maturation-dataset'
    schema_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=200)
    context: Context
    acquisitions: tuple[Acquisition, ...] = Field(min_length=1, max_length=100)
    csv_file: str = Field(min_length=1, max_length=200)
    csv_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    previously_inspected: bool
    synthetic: bool = False
    processing: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def unique_acquisitions(self):
        if len({a.id.casefold() for a in self.acquisitions})!=len(self.acquisitions):
            raise ValueError('Acquisition IDs must be unique.')
        if Path(self.csv_file).name!=self.csv_file or self.csv_file in ('.','..') or '/' in self.csv_file or '\\' in self.csv_file:
            raise ValueError('CSV must be a filename in the manifest directory.')
        return self


def assess(model, dataset, csv_text):
    model=FrozenModel.model_validate(model.model_dump(mode='json'))
    dataset=Dataset.model_validate(dataset.model_dump(mode='json'))
    raw=csv_text.encode('utf-8')
    if len(raw)>1_000_000 or hashlib.sha256(raw).hexdigest()!=dataset.csv_sha256:
        raise ValueError('Measurement file size or hash check failed.')
    reader=csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames != ['acquisition_id','series_id','time_min','fluorescence']:
        raise ValueError('CSV columns must be acquisition_id,series_id,time_min,fluorescence in that order.')
    acquisitions={a.id:a for a in dataset.acquisitions};groups={};n_rows=0
    for row in reader:
        n_rows+=1
        if n_rows>10000 or None in row or any(v is None for v in row.values()) or row['acquisition_id'] not in acquisitions or not row['series_id'].strip():
            raise ValueError('Invalid acquisition, series, or row count.')
        time=float(row['time_min']);value=float(row['fluorescence'])
        if not math.isfinite(time) or not 0<=time<=1e9 or not math.isfinite(value) or value<=0:
            raise ValueError('Times must be finite/nonnegative and fluorescence finite/positive.')
        key=(row['acquisition_id'],row['series_id'].strip())
        groups.setdefault(key,[]).append((time,value))
    if not groups or {k[0] for k in groups}!=set(acquisitions):
        raise ValueError('Every declared acquisition must have measurements.')
    reasons=[];alignment=[]
    if model.context != dataset.context:reasons.append('Biological context differs from the frozen model.')
    if model.synthetic or dataset.synthetic:reasons.append('Synthetic data/model cannot establish biological validation.')
    if dataset.previously_inspected:reasons.append('Evaluation data were previously inspected; this is retrospective.')
    for a in model.training_acquisitions:
        if a.timing_basis not in ('recorded','author_aligned') or a.event_time_min is None:
            reasons.append('Reference-model intervention timing is unresolved.')
        if a.biological_unit_id is None:reasons.append('Reference biological-unit identity is unavailable.')
    train_ids={a.id.casefold() for a in model.training_acquisitions}
    train_hashes={h for a in model.training_acquisitions for h in a.source_hashes}
    train_days={(a.source_id.casefold(),a.date) for a in model.training_acquisitions}
    train_units={a.biological_unit_id.casefold() for a in model.training_acquisitions if a.biological_unit_id}
    for a in dataset.acquisitions:
        if a.id.casefold() in train_ids or (a.source_id.casefold(),a.date) in train_days:
            reasons.append('Training and evaluation share an acquisition or source/date.')
        if train_hashes.intersection(a.source_hashes):reasons.append('Training and evaluation reuse source-file bytes.')
        if a.biological_unit_id is None:reasons.append('Evaluation biological-unit identity is unavailable.')
        elif a.biological_unit_id.casefold() in train_units:reasons.append('Training and evaluation share a biological unit.')
        if a.timing_basis not in ('recorded','author_aligned'):
            reasons.append('Evaluation timing is assumed, inferred from growth, or unknown.')
        if a.event_time_min is None:alignment.append(f'{a.id}: event time is missing; no automatic alignment was performed.')
    normalized=[]
    for (aid,sid),points in sorted(groups.items()):
        points=sorted(points)
        if len({t for t,v in points})!=len(points):raise ValueError('Duplicate times within a series.')
        event=acquisitions[aid].event_time_min
        if event is None:continue
        baseline=[v for t,v in points if t==event]
        positive=[(t,v) for t,v in points if t>event]
        if len(baseline)!=1 or len(positive)<3:
            alignment.append(f'{aid}/{sid}: need a measured event-time baseline and three later points; no interpolation was performed.');continue
        if (positive[-1][0]-event)/60>168:raise ValueError('Evaluation interval exceeds 168 hours.')
        if (positive[-1][0]-event)/60>model.valid_duration_h:
            reasons.append('Evaluation extends beyond the frozen model time range.')
        for t,v in [(event,baseline[0]),*positive]:
            relative=v/baseline[0]
            if not math.isfinite(relative) or relative>1e12:
                raise ValueError('Normalized fluorescence exceeds the supported finite range.')
            normalized.append(dict(acquisition_id=aid,series_id=sid,time_h=(t-event)/60,observed=relative,
                predicted=float(prediction((t-event)/60,model.maturation_per_hour,model.immature_to_initial_mature_ratio))))
    reasons=list(dict.fromkeys(reasons));alignment=list(dict.fromkeys(alignment))
    result=dict(eligible_by_declared_metadata=not reasons and not alignment,exclusions=reasons,alignment_errors=alignment,
        status='CANNOT_ALIGN' if alignment else 'EXPLORATORY_ONLY' if reasons else 'ELIGIBLE_BY_DECLARED_METADATA',
        verification_scope='Supplied metadata and byte consistency only; no source authentication, blinding guarantee, or biological pass/fail.',
        rows=[] if alignment else normalized,metrics=None,per_series={})
    if not alignment:
        positive=[r for r in normalized if r['time_h']>0]
        result['metrics']=metrics([r['observed'] for r in positive],[r['predicted'] for r in positive])
        result['metrics'].update(n_acquisitions=len(acquisitions),n_series=len(groups))
        for key in groups:
            p=[r for r in positive if (r['acquisition_id'],r['series_id'])==key]
            result['per_series'][json.dumps(key)]=metrics([r['observed'] for r in p],[r['predicted'] for r in p])
    return result


def load_inputs(model_path,dataset_path):
    paths=[Path(p).expanduser() for p in (model_path,dataset_path)]
    for p in paths:
        if not p.is_absolute() or not p.is_file() or p.stat().st_size>1_000_000:
            raise ValueError('Choose existing absolute JSON file paths up to 1 MB.')
    model=FrozenModel.model_validate_json(paths[0].read_text())
    dataset=Dataset.model_validate_json(paths[1].read_text())
    data_path=paths[1].parent/dataset.csv_file
    if data_path.is_symlink() or data_path.resolve().parent!=paths[1].parent.resolve() or not data_path.is_file() or data_path.stat().st_size>1_000_000:
        raise ValueError('CSV must be a regular file beside the dataset manifest, up to 1 MB.')
    text=data_path.read_bytes().decode('utf-8')
    return model,dataset,text


def create_report(model,dataset,csv_text,experiment_id):
    return dict(format='virtuallab-maturation-evaluation',schema_version=1,id=str(uuid4()),experiment_id=experiment_id,
        created_at=datetime.now(timezone.utc).isoformat(),epistemic_state='CALCULATED',
        frozen_model=model.model_dump(mode='json'),dataset=dataset.model_dump(mode='json'),csv_text=csv_text,
        assessment=assess(model,dataset,csv_text),
        source_hashes={'validation/maturation.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def validate_report(payload):
    if (payload.get('format')!='virtuallab-maturation-evaluation' or payload.get('schema_version')!=1
            or payload.get('epistemic_state')!='CALCULATED' or not payload.get('id') or not payload.get('experiment_id')):
        raise ValueError('Unsupported maturation evaluation report.')
    actual=assess(FrozenModel.model_validate(payload['frozen_model']),Dataset.model_validate(payload['dataset']),payload['csv_text'])
    if actual != payload['assessment']:raise ValueError('Saved eligibility or metrics disagree with the embedded inputs.')
    return payload
