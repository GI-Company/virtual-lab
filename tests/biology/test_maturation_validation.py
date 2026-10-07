from copy import deepcopy
import math
import numpy as np
import pytest
from virtual_lab.biology.maturation_validation import fit_and_evaluate,prediction,fitted_system
from virtual_lab.biology.simulation import simulate


def dataset():
    return [dict(colony=c,split=split,time_h=float(t),relative_fluorescence=float(1+.2*(1-math.exp(-3*t))))
            for c,split in [('a','train'),('b','train'),('c','holdout')]
            for t in np.linspace(0,2,21)]


def test_known_kinetics_recovered_and_holdout_cannot_change_fit():
    rows=dataset();a=fit_and_evaluate(rows)
    assert a['parameters']['maturation_per_hour']==pytest.approx(3,rel=1e-7)
    assert a['parameters']['immature_to_initial_mature_ratio']==pytest.approx(.2,rel=1e-7)
    for r in rows:
        if r['split']=='holdout' and r['time_h']>0:r['relative_fluorescence']*=2
    b=fit_and_evaluate(rows)
    assert a['parameters']==b['parameters'] and a['metrics']['train']==b['metrics']['train']
    assert b['metrics']['holdout']['rmse']>1


def test_fitted_parameters_reproduce_observation_model_in_persistent_objects():
    fit=fit_and_evaluate(dataset());s=fitted_system(fit,'a'*64)
    r=simulate(s,2,[],'experiment')
    np.testing.assert_allclose(r.protein,prediction(r.time_h,3,.2),atol=1e-9)
    assert max(r.rna)==0
    assert s.mechanism.parameters['maturation'].evidence.state.value=='INFERRED'
    assert next(o for o in s.objects if o.kind=='immature_protein').state.evidence.state.value=='INFERRED'
    assert next(o for o in r.final_system.objects if o.kind=='protein').state.evidence.state.value=='SIMULATED'


@pytest.mark.parametrize('fault',['nan','negative','duplicate','cross_split','missing_baseline','wrong_baseline','no_holdout'])
def test_invalid_validation_dataset_rejected(fault):
    rows=dataset()
    if fault=='nan':rows[1]['relative_fluorescence']=float('nan')
    if fault=='negative':rows[1]['time_h']=-1
    if fault=='duplicate':rows.append(deepcopy(rows[1]))
    if fault=='cross_split':rows[1]['split']='holdout'
    if fault=='missing_baseline':rows=[r for r in rows if r['time_h']>0]
    if fault=='wrong_baseline':rows[0]['relative_fluorescence']=2
    if fault=='no_holdout':rows=[r for r in rows if r['split']=='train']
    with pytest.raises(ValueError):fit_and_evaluate(rows)
