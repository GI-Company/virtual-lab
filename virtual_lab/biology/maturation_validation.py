"""Retrospective colony-level assessment of a one-step maturation observation model.

These utilities do not establish independent experimental validation. Colony
normalization must use only its time-zero baseline, never its future plateau.
"""
import math
import numpy as np
from scipy.optimize import least_squares


def prediction(time_h, rate, capacity):
    return 1 + capacity * (-np.expm1(-rate * np.asarray(time_h)))


def validate_rows(rows):
    groups={}
    for row in rows:
        colony=row['colony'];split=row['split']
        if not isinstance(colony,str) or not colony.strip() or split not in ('train','holdout'):
            raise ValueError('Every row needs a colony ID and declared split.')
        group=groups.setdefault(colony,[]);group.append(row)
        for key in ('time_h','relative_fluorescence'):
            value=row[key]
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError('Times and fluorescence must be finite.')
        if not 0 <= row['time_h'] <= 48 or row['relative_fluorescence'] <= 0:
            raise ValueError('Unsupported time or nonpositive fluorescence.')
    if not groups or {r['split'] for r in rows} != {'train','holdout'}:
        raise ValueError('Training and held-out colonies are required.')
    for group in groups.values():
        times=[r['time_h'] for r in group]
        if len({r['split'] for r in group})!=1 or len(set(times))!=len(times):
            raise ValueError('Colonies cannot cross splits or have duplicate times.')
        if len(times)<4 or 0 not in times or sum(t>0 for t in times)<3:
            raise ValueError('Each colony needs a baseline and three positive times.')
        if next(r['relative_fluorescence'] for r in group if r['time_h']==0)!=1:
            raise ValueError('Baseline-normalized fluorescence must start at one.')
    return groups


def metrics(actual,predicted):
    actual=np.asarray(actual);predicted=np.asarray(predicted)
    error=predicted-actual;sst=float(np.sum((actual-actual.mean())**2))
    return dict(n_points=len(actual),rmse=float(np.sqrt(np.mean(error**2))),
        mae=float(np.mean(abs(error))),r_squared=None if sst<1e-15 else float(1-np.sum(error**2)/sst),
        no_maturation_rmse=float(np.sqrt(np.mean((actual-1)**2))))


def fit_and_evaluate(rows):
    groups=validate_rows(rows)
    training=[r for r in rows if r['split']=='train' and r['time_h']>0]
    counts={c:sum(r['time_h']>0 for r in g) for c,g in groups.items()}
    t=np.array([r['time_h'] for r in training]);y=np.array([r['relative_fluorescence'] for r in training])
    weights=np.array([1/math.sqrt(counts[r['colony']]) for r in training])
    fits=[least_squares(lambda x:(prediction(t,*x)-y)*weights,[k,a],bounds=([.001,0],[100,10]),
                       ftol=1e-12,xtol=1e-12,gtol=1e-12,max_nfev=5000)
          for k in (.1,1.,10.,50.) for a in (.1,1.,5.)]
    fits=[f for f in fits if f.success and np.isfinite(f.x).all()]
    if not fits:raise ValueError('Maturation fit failed to converge.')
    best=min(fits,key=lambda f:float(np.sum(f.fun**2)));rate,capacity=map(float,best.x)
    result=dict(parameters=dict(maturation_per_hour=rate,immature_to_initial_mature_ratio=capacity,
                                maturation_half_time_min=60*math.log(2)/rate),
                parameter_state='INFERRED',method='Equal-colony-weight bounded least squares; fixed 12 starts; training only',
                bounds=dict(maturation_per_hour=[.001,100],immature_to_initial_mature_ratio=[0,10]),
                boundary_solution=bool(np.any(best.active_mask)),metrics={},per_colony={})
    for split in ('train','holdout'):
        subset=[r for r in rows if r['split']==split and r['time_h']>0]
        result['metrics'][split]=metrics([r['relative_fluorescence'] for r in subset],prediction([r['time_h'] for r in subset],rate,capacity))
        result['metrics'][split]['n_colonies']=sum(g[0]['split']==split for g in groups.values())
    for colony,group in groups.items():
        positive=[r for r in group if r['time_h']>0]
        result['per_colony'][colony]=dict(split=group[0]['split'],**metrics([r['relative_fluorescence'] for r in positive],prediction([r['time_h'] for r in positive],rate,capacity)))
    return result


def fitted_system(result,source_sha256):
    """Create a scoped probe with inferred maturation and initial immature pool.

This report reference must be distributed alongside the study; this helper does
not assert the source report's authenticity or mark the whole system calibrated.
"""
    from .objects import starter_system,BiologicalSystem,Evidence
    from virtual_lab.domain.epistemics import EpistemicState
    p=result['parameters']
    s=starter_system(name='mEGFP effective post-baseline model',gene_label='mEGFP',
        organism='Escherichia coli MG1655',context='37 C; Balleza et al. archive 2016-06-23; frame-61 baseline; actual arrest timing unresolved; survivor colonies',
        model_id='maturing_gene_expression',initial_protein=1,initial_immature_protein=p['immature_to_initial_mature_ratio'],
        parameters=dict(transcription=0,translation=0,rna_decay=0,protein_decay=0,maturation=p['maturation_per_hour']))
    raw=s.model_dump(mode='json')
    evidence=Evidence(state=EpistemicState.INFERRED,source='Maturation assessment report SHA256 '+source_sha256,
        scope='Fitted only to four training colonies from one acquisition; held-out colonies share that experiment. Effective post-baseline rate, not a confirmed full maturation constant. Growth slowdown precedes nominal onset; negligible turnover is assumed.').model_dump(mode='json')
    raw['mechanism']['parameters']['maturation']['evidence']=evidence
    raw['mechanism']['scope']='One-step maturation of a pre-existing pool; fluorescence proportional to mature protein; no production or turnover; report must accompany this study.'
    for obj in raw['objects']:
        if obj['kind']=='immature_protein':obj['state']['evidence']=evidence
        if obj['kind']=='protein':obj['state']['evidence']=Evidence(state=EpistemicState.DERIVED,
            source='Each colony fluorescence divided by its own nominal-onset baseline',
            scope='Observation-model normalization; not an absolute molecule count.').model_dump(mode='json')
    return BiologicalSystem.model_validate(raw)
