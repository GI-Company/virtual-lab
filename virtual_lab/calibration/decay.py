"""Reproducible first-order mRNA-decay calibration against explicit replicate splits."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import io
import json
import math
import uuid

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.integrate import solve_ivp

DATA = Path(__file__).with_name('data')


def load_benchmark():
    meta = json.loads((DATA/'pgk1_decay.json').read_text())
    raw = (DATA/'pgk1_decay.csv').read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['csv_sha256']:
        raise ValueError('Bundled measurements failed their integrity check.')
    return meta, read_measurements(raw)


def read_measurements(raw):
    if len(raw) > 1_000_000:
        raise ValueError('Measurement CSV exceeds 1 MB.')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    required = {'sample_id', 'replicate', 'split', 'time_min', 'value'}
    if set(reader.fieldnames or ()) != required:
        raise ValueError('CSV requires sample_id,replicate,split,time_min,value columns.')
    rows = []
    for row in reader:
        if len(rows) >= 1000 or None in row:
            raise ValueError('Too many rows or malformed CSV.')
        for key in ('time_min', 'value'):
            row[key] = float(row[key])
        rows.append(row)
    validate_measurements(rows)
    return rows


def validate_measurements(rows):
    if not 6 <= len(rows) <= 1000:
        raise ValueError('Provide 6–1000 measurements with training and held-out replicates.')
    ids, replicates = set(), {}
    for row in rows:
        sid, rep = row['sample_id'], row['replicate']
        if not isinstance(sid, str) or not sid.strip() or sid in ids or not isinstance(rep, str) or not rep.strip():
            raise ValueError('Sample IDs must be unique and replicate IDs nonempty.')
        ids.add(sid)
        if row['split'] not in ('train', 'holdout'):
            raise ValueError('Split must be train or holdout.')
        if rep in replicates and replicates[rep] != row['split']:
            raise ValueError('A biological replicate cannot cross the training/holdout split.')
        replicates[rep] = row['split']
        for key in ('time_min', 'value'):
            v = row[key]
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v):
                raise ValueError('Measurements and times must be finite numbers.')
        if not 0 <= row['time_min'] <= 2880:
            raise ValueError('Times must lie between 0 and 2880 minutes.')
    if set(replicates.values()) != {'train', 'holdout'}:
        raise ValueError('Both training and held-out replicates are required.')
    for rep in replicates:
        group = [r for r in rows if r['replicate'] == rep]
        if not any(r['time_min'] == 0 for r in group):
            raise ValueError('Every replicate requires a time-zero baseline.')
        if len({r['time_min'] for r in group if r['time_min'] > 0}) < 2:
            raise ValueError('Every replicate requires at least two positive time points.')


def normalize(rows, scale):
    validate_measurements(rows)
    if scale not in ('log2', 'linear'):
        raise ValueError('Declare log2 or linear input scale explicitly.')
    result = [dict(r) for r in rows]
    for rep in {r['replicate'] for r in rows}:
        group = [r for r in result if r['replicate'] == rep]
        values = np.array([r['value'] for r in group], float)
        zero = np.array([r['time_min'] == 0 for r in group])
        if scale == 'log2':
            # Shift before exponentiating to avoid overflow; arithmetic mean on linear scale.
            with np.errstate(over='ignore', invalid='ignore'):
                linear = np.exp2(values - values[zero].max())
        else:
            linear = values
        if not np.isfinite(linear).all() or (linear <= 0).any():
            raise ValueError('Intensity values must map to finite positive abundances.')
        baseline = float(linear[zero].mean())
        if not math.isfinite(baseline) or baseline <= 0:
            raise ValueError('Invalid time-zero normalization baseline.')
        relative = linear / baseline
        if not np.isfinite(relative).all() or (relative > 1e6).any():
            raise ValueError('Normalized intensity is outside the supported range.')
        for row, value in zip(group, relative):
            row['relative_abundance'] = float(value)
    return result


def fit_decay(rows, metadata, experiment_id=''):
    """Fit only positive-time training points; never tune parameters on holdout."""
    scale = metadata.get('value_scale')
    normalized = normalize(rows, scale)
    train = [r for r in normalized if r['split'] == 'train' and r['time_min'] > 0]
    t = np.array([r['time_min']/60 for r in train])
    y = np.array([r['relative_abundance'] for r in train])
    def loss(k): return float(np.sum((np.exp(-k*t)-y)**2))
    optimum = minimize_scalar(loss, bounds=(0, 120), method='bounded', options={'xatol':1e-10})
    if not optimum.success:
        raise ValueError('Decay fit did not converge.')
    k = min((0., float(optimum.x), 120.), key=loss)
    metrics = {}
    for split in ('train', 'holdout'):
        group = [r for r in normalized if r['split'] == split and r['time_min'] > 0]
        actual = np.array([r['relative_abundance'] for r in group])
        predicted = np.exp(-k*np.array([r['time_min']/60 for r in group]))
        sst = float(np.sum((actual-actual.mean())**2))
        metrics[split] = dict(n=len(group), rmse=float(np.sqrt(np.mean((predicted-actual)**2))),
            mae=float(np.mean(abs(predicted-actual))),
            r_squared=None if sst < 1e-15 else float(1-np.sum((predicted-actual)**2)/sst),
            no_decay_rmse=float(np.sqrt(np.mean((1-actual)**2))))
    for row in normalized:
        row['predicted_abundance'] = float(np.exp(-k*row['time_min']/60))
        row['residual'] = row['relative_abundance']-row['predicted_abundance']
    times = np.linspace(0, max(r['time_min'] for r in rows)/60, 121)
    exact = np.exp(-k*times)
    numeric = solve_ivp(lambda t,y: -k*y, (0,float(times[-1])), [1.], t_eval=times,
                        method='DOP853', rtol=1e-10, atol=1e-12)
    if not numeric.success:
        raise ValueError('Independent ODE integration failed.')
    error = float(np.max(abs(exact-numeric.y[0])))
    bound = k == 0 or k == 120
    return dict(format='virtuallab-decay-calibration', schema_version=1, id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(), experiment_id=experiment_id,
        epistemic_state='INFERRED', model_id='first_order_mrna_decay', model_version='1.0.0',
        equation='dm/dt = -k*m; m(0)=1; t in hours',
        dataset=json.loads(json.dumps(metadata, allow_nan=False)), measurements=normalized,
        parameters=dict(decay_per_hour=k, half_life_min=None if k==0 else 60*math.log(2)/k),
        fit=dict(method='bounded unweighted least squares on relative abundance', bounds_per_hour=[0,120],
                 boundary_solution=bound, time_zero_use='Normalization only; excluded from objective and metrics',
                 uncertainty='No confidence interval estimated; one training biological replicate in bundled benchmark.'),
        metrics=metrics, validation_status='BOUNDARY_FIT' if bound else 'HOLDOUT_EVALUATED',
        validation_scope='Same-study held-out biological replicate, conditioned on its observed baseline; not independent-laboratory validation.',
        curve=dict(time_min=(times*60).tolist(), relative_abundance=exact.tolist(), epistemic_state='SIMULATED'),
        numerical_check=dict(max_absolute_error=error, passed=error<1e-7, reference='DOP853 against analytic exponential'),
        normalization='Linear intensity divided by mean time-zero technical replicate intensity, separately per biological replicate.',
        source_hashes={'calibration/decay.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        limitations=[*metadata.get('limitations',[]), 'Exponential decay and complete transcription arrest are model assumptions.',
                     'Holdout metrics are reported without a biological pass/fail threshold.'])
