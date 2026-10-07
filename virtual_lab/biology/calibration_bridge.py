"""Transfer a scoped RNA-decay fit without claiming calibrated protein behavior."""
import hashlib
import json
import math
from functools import lru_cache

from virtual_lab.calibration.decay import fit_decay
from virtual_lab.domain.epistemics import EpistemicState


def canonical(result):
    text = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(text.encode()) > 1_000_000:
        raise ValueError('Calibration record exceeds 1 MB.')
    return text


@lru_cache(maxsize=16)
def checked_fit(text):
    result = json.loads(text)
    if (result.get('format') != 'virtuallab-decay-calibration' or result.get('schema_version') != 1
            or result.get('epistemic_state') != 'INFERRED' or result.get('model_id') != 'first_order_mrna_decay'
            or result.get('model_version') != '1.0.0' or not result.get('id')):
        raise ValueError('Unsupported RNA decay calibration.')
    meta = result['dataset']
    if any(not isinstance(meta.get(k), str) or not meta[k].strip() for k in ('gene', 'organism', 'condition')):
        raise ValueError('Calibration transfer requires separate gene, organism, and condition metadata; free-text local context is insufficient.')
    # Refit declared training values; do not trust an edited rate or holdout metrics.
    rows = [{k:r[k] for k in ('sample_id','replicate','split','time_min','value')} for r in result['measurements']]
    verified = fit_decay(rows, meta, result.get('experiment_id', ''))
    k = result['parameters']['decay_per_hour']
    if isinstance(k, bool) or not isinstance(k, (int,float)) or not math.isfinite(k) or not 0 <= k <= 100:
        raise ValueError('Fitted rate is outside the biological mechanism range (0–100/h).')
    if not math.isclose(k, verified['parameters']['decay_per_hour'], rel_tol=1e-8, abs_tol=1e-10):
        raise ValueError('Calibration rate disagrees with the training measurements.')
    for split in ('train', 'holdout'):
        for metric, value in verified['metrics'][split].items():
            actual = result['metrics'][split].get(metric)
            if value is None:
                valid = actual is None
            else:
                valid = isinstance(actual,(int,float)) and not isinstance(actual,bool) and math.isfinite(actual) and math.isclose(actual,value,rel_tol=1e-8,abs_tol=1e-10)
            if not valid:
                raise ValueError('Calibration metrics disagree with the declared measurements.')
    return k, hashlib.sha256(text.encode()).hexdigest()


def validate_calibrated_system(system):
    result = system.calibration_result
    k, sha = checked_fit(canonical(result))
    meta = result['dataset']
    gene = next(o for o in system.objects if o.kind == 'gene')
    if (gene.identity.label, gene.identity.organism, system.context) != (meta['gene'], meta['organism'], meta['condition']):
        raise ValueError('Calibrated identity and conditions must match the source dataset.')
    if system.mechanism.model_id != 'linear_gene_expression':
        raise ValueError('RNA-only calibration does not establish a protein maturation model.')
    rates=system.mechanism.parameters
    if any(rates[key].value != 0 for key in ('transcription','translation','protein_decay')):
        raise ValueError('The calibration-derived probe isolates RNA decay; protein and production rates must remain zero.')
    if rates['rna_decay'].value != k or rates['rna_decay'].evidence.state != EpistemicState.INFERRED:
        raise ValueError('RNA rate must retain its fitted value and INFERRED evidence.')
    if rates['rna_decay'].evidence.source != f"Calibration {result['id']}; SHA256 {sha}":
        raise ValueError('RNA rate calibration reference mismatch.')
    if system.revision == 0:
        abundances={o.kind:o.state.abundance for o in system.objects}
        if abundances != {'gene':1., 'rna':1., 'protein':0.}:
            raise ValueError('A calibrated decay probe starts at normalized RNA one, protein zero, and one gene copy.')


def system_from_calibration(result):
    from .objects import starter_system, BiologicalSystem, Evidence
    text=canonical(result);k,sha=checked_fit(text)
    result=json.loads(text);meta=result['dataset']
    system=starter_system(name=meta['gene']+' calibrated RNA-decay probe', gene_label=meta['gene'],
        organism=meta['organism'],context=meta['condition'],initial_rna=1.,
        parameters=dict(transcription=0.,translation=0.,rna_decay=k,protein_decay=0.))
    raw=system.model_dump(mode='json');raw['calibration_result']=result
    raw['mechanism']['scope']='RNA decay only in the source conditions. No protein calibration; production and protein pool are disabled.'
    raw['mechanism']['parameters']['rna_decay']['evidence']=Evidence(state=EpistemicState.INFERRED,
        source=f"Calibration {result['id']}; SHA256 {sha}",
        scope='Fitted to training data; same-study holdout evaluation is not independent biological validation.').model_dump(mode='json')
    return BiologicalSystem.model_validate(raw)
