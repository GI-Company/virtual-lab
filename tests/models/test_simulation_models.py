from dataclasses import replace
from pathlib import Path
import numpy as np
import pytest

from virtual_lab.gui.services.simulation_runner import RunConfig, run_simulation, RunCancelled
from virtual_lab.gui.services.simulation_result import SimulationResult
from virtual_lab.models.registry import get_model, register_model, ModelSpec, ParameterSpec, StateSpec
from virtual_lab.domain.assemblers import simulation_result_to_observation


def exact_gene(t, controls, concentration):
    f = controls['transcription'] * (1 + controls['induction'] * concentration / (controls['ec50'] + concentration))
    a, b, k = controls['mrna_decay'], controls['protein_decay'], controls['translation']
    m = f / a * (1 - np.exp(-a*t))
    decay_integral = t*np.exp(-a*t) if a == b else (np.exp(-a*t)-np.exp(-b*t))/(b-a)
    p = k*f/a * ((1-np.exp(-b*t))/b-decay_integral)
    return np.array([m, p])


@pytest.mark.parametrize('decay', [.1, .5])
def test_gene_expression_matches_closed_form(decay):
    cfg = RunConfig(model_id='gene_expression', members=4, duration_h=12, variation=0,
                    model_parameters={'protein_decay': decay})
    result = run_simulation(cfg)
    controls = get_model('gene_expression').validated_parameters(cfg.model_parameters)
    for concentration, key in [(cfg.concentration_um, 'final_state'), (0, 'control_final_state')]:
        np.testing.assert_allclose(result[key], np.tile(exact_gene(cfg.duration_h, controls, concentration), (cfg.members, 1)), rtol=1e-8, atol=1e-9)
    assert result['numerical_check']['status'] == 'PASSED'
    assert result['epistemic_state'] == 'SIMULATED'
    assert result['parameter_epistemic_state'] == 'MODEL_ASSUMPTION'
    assert result['model_version'] == '1.0.0'
    assert result['resolved_parameters'] == controls
    assert result['config']['model_parameters'] == controls
    assert 'rescue_max' not in result['config']
    assert len(result['source_hashes']) >= 4


def test_zero_stimulus_pairs_and_reproducible_ensemble():
    cfg = RunConfig(model_id='gene_expression', concentration_um=0, duration_h=1, members=8)
    first, second = run_simulation(cfg), run_simulation(cfg)
    assert first['final_state'] == first['control_final_state']
    assert first['parameter_samples'] == second['parameter_samples']
    assert first['final_state'] == second['final_state']
    assert first['id'] != second['id']


@pytest.mark.parametrize('params', [{'typo':1}, {'mrna_decay':-1}, {'translation':float('nan')}, {'induction':True}])
def test_bad_model_parameters_rejected(params):
    with pytest.raises(ValueError):
        run_simulation(RunConfig(model_id='gene_expression', model_parameters=params))


def test_cancelled_model_has_no_result():
    with pytest.raises(RunCancelled):
        run_simulation(RunConfig(model_id='gene_expression'), cancelled=lambda: True)


def test_rho_backward_compatible_controls():
    legacy = RunConfig(members=4, duration_h=1, ec50_um=2, rescue_max=.3, erad_multiplier=1.2)
    explicit = replace(legacy, model_parameters={'ec50':2, 'rescue_max':.3, 'erad_multiplier':1.2})
    a, b = run_simulation(legacy), run_simulation(explicit)
    assert a['final_state'] == b['final_state']
    assert len(a['state_metadata']) == 5
    assert a['model_id'] == 'rho_p23h'
    old = dict(a);old.pop('state_metadata');old.pop('model_id');old.pop('model_label')
    assert SimulationResult.from_dict(old).model_id == 'rho_p23h'


def test_third_party_model_runs_without_core_changes(monkeypatch):
    import virtual_lab.models.registry as registry
    get_model('rho_p23h')
    monkeypatch.setattr(registry, '_MODELS', dict(registry._MODELS))
    class Decay:
        def initial_state(self): return np.ones(1)
        def state_schema(self): return ['quantity']
        def rhs(self,t,y,params,exposure,xp=np): return -params['decay']*y
    spec = ModelSpec(id='test_decay', label='Independent decay', version='1', description='Test',
                     factory=Decay, parameters=(ParameterSpec('decay','Decay',.2,.01,1,'1/h'),),
                     states=(StateSpec('quantity','Quantity'),), source_files=(Path(__file__),), limitations=('Test model',))
    register_model(spec)
    result = run_simulation(RunConfig(model_id='test_decay', members=3, duration_h=2, variation=0))
    np.testing.assert_allclose(result['final_state'], np.full((3,1), np.exp(-.4)), rtol=1e-9)
    with pytest.raises(ValueError, match='Duplicate model'): register_model(spec)


def test_model_specific_observation_semantics():
    result = run_simulation(RunConfig(model_id='gene_expression', duration_h=1, members=2))
    observation = simulation_result_to_observation(result, 'gene-study')
    assert [q.symbol for q in observation.quantities] == ['mrna','protein']
    assert all('rho' not in q.semantic_name for q in observation.quantities)
    restored = SimulationResult.from_dict(result)
    assert restored.control_trajectory['median'].shape == (97,2)
    assert restored.model_id == 'gene_expression'


def test_gui_model_selection_analysis_and_rho_views(qtbot):
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from virtual_lab.gui.experiments.experiment_workspace import ExperimentWorkspace
    from virtual_lab.gui.analysis.analysis_workspace import AnalysisWorkspace
    from virtual_lab.gui.world.cell_view import CellView
    from virtual_lab.gui.world.tissue_view import TissueView
    state = WorkspaceState()
    panel = ExperimentWorkspace(state); analysis = AnalysisWorkspace(state)
    cell, tissue = CellView(state), TissueView(state)
    for widget in (panel, analysis, cell, tissue): qtbot.addWidget(widget)
    panel.model_selector.setCurrentIndex(panel.model_selector.findData('gene_expression'))
    assert 'transcription' in panel.model_fields and 'rescue_max' not in panel.model_fields
    result = run_simulation(RunConfig(model_id='gene_expression', duration_h=1, members=4))
    state.current_result = SimulationResult.from_dict(result)
    assert analysis.list_endpoints.count() == 2
    analysis.list_endpoints.setCurrentRow(1)
    assert 'Protein abundance' in analysis.lbl_dist_title.text()
    assert cell.scene.items() == []
    assert tissue.result is None
    assert 'Spearman' in analysis.lbl_prcc_title.text()


def test_installed_entrypoint_load_is_atomic(monkeypatch):
    import virtual_lab.models.registry as registry
    from virtual_lab.models.builtin import GENE_EXPRESSION
    spec = replace(GENE_EXPRESSION, id='installed_gene')
    class Entry:
        def load(self): return lambda: spec
    monkeypatch.setattr(registry, '_MODELS', {})
    monkeypatch.setattr(registry, '_LOADED', False)
    monkeypatch.setattr(registry, 'entry_points', lambda **kw: [Entry(), Entry()])
    with pytest.raises(ValueError, match='Duplicate model'):
        registry.models()
    assert not registry._LOADED and not registry._MODELS
    monkeypatch.setattr(registry, 'entry_points', lambda **kw: [Entry()])
    assert registry.get_model('installed_gene') == spec
    assert len(registry.models()) == 3
