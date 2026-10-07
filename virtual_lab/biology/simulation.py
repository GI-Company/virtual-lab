"""Piecewise exact linear evolution with persistent identity and intervention history."""
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
from typing import Literal
import numpy as np
from pydantic import Field, model_validator
from scipy.linalg import expm

from .objects import Record, BiologicalSystem, Evidence, Intervention, uid
from .mechanisms import get_mechanism
from virtual_lab.domain.epistemics import EpistemicState


class BiologicalRun(Record):
    format: Literal['virtuallab-biological-run'] = 'virtuallab-biological-run'
    schema_version: Literal[1] = 1
    id: str = Field(default_factory=uid)
    experiment_id: str = Field(min_length=1)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    epistemic_state: Literal['SIMULATED'] = 'SIMULATED'
    initial_system: BiologicalSystem
    final_system: BiologicalSystem
    interventions: tuple[Intervention, ...] = Field(max_length=64)
    time_h: tuple[float, ...] = Field(min_length=2, max_length=1000)
    rna: tuple[float, ...]
    protein: tuple[float, ...]
    immature_protein: tuple[float, ...] | None = None
    source_hashes: dict[str, str]
    method: Literal['piecewise matrix exponential'] = 'piecewise matrix exponential'
    limitations: tuple[str, ...] = (
        'Illustrative assumed rates; no biological validation is established.',
        'Names, accessions, variants, sequences, and compartments do not change the equations.',
        'No feedback, transport, binding, cell division, resource limits, or stochastic effects.',
        'Normalized abundance is not a measured concentration or a molecule count.',
    )

    @model_validator(mode='after')
    def consistent(self):
        a, b = self.initial_system, self.final_system
        if a.calibration_result is not None and a.calibration_result.get('experiment_id') != self.experiment_id:
            raise ValueError('Calibration belongs to a different experiment.')
        if b.id != a.id or b.revision != a.revision+1 or b.last_result_id != self.id:
            raise ValueError('Biological system lineage mismatch.')
        if (b.name, b.context, b.mechanism, b.calibration_result) != (a.name, a.context, a.mechanism, a.calibration_result):
            raise ValueError('A run cannot silently change identity, context, or mechanism.')
        if [o.model_dump(exclude={'state'}) for o in a.objects] != [o.model_dump(exclude={'state'}) for o in b.objects]:
            raise ValueError('Object identities changed during a run.')
        if b.history != a.history+self.interventions:
            raise ValueError('Intervention history mismatch.')
        if any(e.time_h < a.time_h or e.time_h > b.time_h for e in self.interventions):
            raise ValueError('Intervention is outside the run interval.')
        if len({(e.time_h, e.target) for e in self.interventions}) != len(self.interventions):
            raise ValueError('Conflicting interventions at the same time.')
        for target in ('transcription', 'translation'):
            expected = getattr(a, target+'_multiplier')
            for event in self.interventions:
                if event.target == target:
                    expected = event.multiplier
            if getattr(b, target+'_multiplier') != expected:
                raise ValueError('Final mechanism multiplier disagrees with history.')
        if len(self.rna) != len(self.time_h) or len(self.protein) != len(self.time_h):
            raise ValueError('Trajectory lengths disagree.')
        if self.time_h[0] != a.time_h or self.time_h[-1] != b.time_h or any(x >= y for x,y in zip(self.time_h,self.time_h[1:])):
            raise ValueError('Trajectory times must strictly increase between snapshot times.')
        kinds = get_mechanism(a.mechanism.model_id, a.mechanism.version).dynamic_kinds
        if ('immature_protein' in kinds) != (self.immature_protein is not None):
            raise ValueError('Immature protein trajectory must match the mechanism.')
        for kind in kinds:
            values = getattr(self, kind)
            if len(values) != len(self.time_h):
                raise ValueError('Trajectory lengths disagree.')
            if any(not math.isfinite(v) or v < 0 for v in values):
                raise ValueError('Trajectory abundance must be finite and nonnegative.')
            for system, endpoint in ((a, values[0]), (b, values[-1])):
                if next(o.state.abundance for o in system.objects if o.kind == kind) != endpoint:
                    raise ValueError('Snapshot abundance disagrees with trajectory.')
            state = next(o.state for o in b.objects if o.kind == kind)
            if state.evidence.state != EpistemicState.SIMULATED:
                raise ValueError('Evolved RNA and protein states must be SIMULATED.')
        if next(o.state for o in a.objects if o.kind=='gene') != next(o.state for o in b.objects if o.kind=='gene'):
            raise ValueError('This mechanism does not change gene copy number.')
        return self


def simulate(system, duration_h, interventions, experiment_id):
    # Round-trip validation rejects mutated nested mappings, including malformed rates.
    system = BiologicalSystem.model_validate(system.model_dump(mode='json'))
    if isinstance(duration_h, bool) or not math.isfinite(duration_h) or not 0.01 <= duration_h <= 168:
        raise ValueError('Run duration must be 0.01–168 hours.')
    end = system.time_h + duration_h
    events = tuple(sorted((Intervention.model_validate(e.model_dump(mode='json')) for e in interventions), key=lambda e:e.time_h))
    if len(events)>64 or len(events)+len(system.history)>1000:
        raise ValueError('Too many interventions.')
    if any(e.time_h < system.time_h or e.time_h > end for e in events):
        raise ValueError('Intervention must lie within the next run interval.')
    if len({e.id for e in system.history+events}) != len(system.history+events):
        raise ValueError('Intervention IDs must be unique.')
    if len({(e.time_h,e.target) for e in events}) != len(events):
        raise ValueError('Conflicting interventions at the same time.')
    times = sorted(set(np.linspace(system.time_h,end,201).tolist()+[e.time_h for e in events]))
    spec=get_mechanism(system.mechanism.model_id,system.mechanism.version)
    kinds=spec.dynamic_kinds
    y = np.array([next(o.state.abundance for o in system.objects if o.kind==kind) for kind in kinds]+[1.])
    trajectory=[y.copy()]
    modifiers=dict(transcription=system.transcription_multiplier,translation=system.translation_multiplier)
    spec=get_mechanism(system.mechanism.model_id,system.mechanism.version)
    for left,right in zip(times,times[1:]):
        for event in events:
            if event.time_h==left: modifiers[event.target]=event.multiplier
        y=expm(spec.matrix(system,modifiers['transcription'],modifiers['translation'])*(right-left)) @ y
        if not np.isfinite(y).all() or np.min(y[:-1]) < -1e-9 or np.max(y[:-1])>1e12:
            raise ValueError('Evolution produced an invalid abundance.')
        y[:-1]=np.maximum(y[:-1],0.)
        trajectory.append(y.copy())
    for event in events:
        if event.time_h==end: modifiers[event.target]=event.multiplier
    run_id=uid()
    final=system.model_dump(mode='json')
    final.update(revision=system.revision+1,time_h=end,last_result_id=run_id,
                 history=[e.model_dump(mode='json') for e in system.history+events],
                 transcription_multiplier=modifiers['transcription'],translation_multiplier=modifiers['translation'])
    for obj in final['objects']:
        if obj['kind'] in kinds:
            obj['state']['abundance']=float(y[kinds.index(obj['kind'])])
            obj['state']['evidence']=Evidence(state=EpistemicState.SIMULATED,source='Biological run '+run_id,
                scope='Evolution under the declared mechanism and interventions.').model_dump(mode='json')
    trace=np.array(trajectory)
    return BiologicalRun(id=run_id,experiment_id=experiment_id,initial_system=system,
        final_system=BiologicalSystem.model_validate(final),interventions=events,
        time_h=tuple(times), **{kind:tuple(trace[:,i]) for i,kind in enumerate(kinds)},
        source_hashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                       for name in ('objects.py','mechanisms.py','simulation.py','calibration_bridge.py')})
