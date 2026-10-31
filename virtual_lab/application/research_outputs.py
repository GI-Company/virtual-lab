"""Deterministic research outputs; no AI or remote services."""
import csv
import io
import os
from pathlib import Path
import tempfile

import numpy as np


def publish_new_file(destination, raw):
    """Publish complete bytes without overwriting an existing researcher file."""
    destination = Path(destination).expanduser()
    if not destination.is_absolute():
        raise ValueError('Use an absolute output path.')
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.partial', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(temporary, destination)
        except FileExistsError:
            raise ValueError('Choose a new filename; existing files are preserved.') from None
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def simulation_arrays(result):
    states = result.get('state_metadata', [])
    values = np.asarray(result['final_state'], dtype=float)
    controls = np.asarray(result['control_final_state'], dtype=float)
    times = np.asarray(result['times_h'], dtype=float)
    if (not states or values.ndim != 2 or controls.shape != values.shape or not len(values)
            or values.shape[1] != len(states) or times.ndim != 1 or len(times) < 2
            or not np.isfinite(values).all() or not np.isfinite(controls).all()
            or not np.isfinite(times).all() or not np.all(np.diff(times) > 0)
            or result.get('epistemic_state') != 'SIMULATED'):
        raise ValueError('Saved simulation has invalid state or time metadata.')
    return states, values, controls, times


def compare_simulations(a, b):
    states_a, values_a, _, times_a = simulation_arrays(a)
    states_b, values_b, _, times_b = simulation_arrays(b)
    if ((a.get('model_id'), a.get('model_version')) != (b.get('model_id'), b.get('model_version'))
            or times_a[0] != times_b[0] or times_a[-1] != times_b[-1]):
        raise ValueError('Choose the same model/version and simulation time span for comparison.')
    rows = []
    for i, state in enumerate(states_a):
        matches = [(j, other) for j, other in enumerate(states_b) if state.get('semantic_name')
                   and state['semantic_name'] == other.get('semantic_name')
                   and state['units'] == other['units']
                   and state['physical_dimension'] == other['physical_dimension']]
        if len(matches) != 1:
            raise ValueError('Saved runs do not have unambiguous matching state semantics and units.')
        j, _ = matches[0]
        qa, qb = np.quantile(values_a[:, i], [.05, .5, .95]), np.quantile(values_b[:, j], [.05, .5, .95])
        rows.append(dict(state=state['label'], units=state['units'], a=qa.tolist(), b=qb.tolist(), delta=float(qb[1]-qa[1])))
    return rows


def simulation_csv(result):
    states, _, _, times = simulation_arrays(result)
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['run_id', 'experiment_id', 'epistemic_state', 'model_id', 'time_h', 'scenario',
                     'state', 'units', 'p05', 'median', 'p95'])
    for name, key in [('exposure', 'treated_quantiles'), ('control', 'control_quantiles')]:
        quantiles = np.asarray(result[key], dtype=float)
        if quantiles.shape != (len(times), 3, len(states)) or not np.isfinite(quantiles).all():
            raise ValueError('Saved simulation trajectories have invalid dimensions or values.')
        for t, row in zip(times, quantiles):
            for i, state in enumerate(states):
                writer.writerow([result['id'], result.get('experiment_id', ''), 'SIMULATED',
                    result['model_id'], float(t), name, state['key'], state['units'], *row[:, i].tolist()])
    return stream.getvalue().encode('utf-8')
