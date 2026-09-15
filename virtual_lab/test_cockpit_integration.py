import json
import numpy as np
import pytest
from virtual_lab.gui.services.simulation_runner import RunConfig,run_simulation,RunCancelled
from virtual_lab.gui.services.run_store import RunStore
from virtual_lab.gui.services.mapping import StructureMappingService,StructureResidueRef
from virtual_lab.gui.services.molecule_design import build_design

def test_paired_vehicle_reproducibility_and_reference():
    cfg=RunConfig(members=4,duration_h=1,concentration_um=0)
    a=run_simulation(cfg);b=run_simulation(cfg)
    assert a['final_state']==b['final_state']==a['control_final_state']
    assert a['numerical_check']['status']=='PASSED'
    assert len(a['times_h'])==97
    assert len(a['source_hashes']['processes.py'])==64

def test_actual_intervention_changes_model():
    a=run_simulation(RunConfig(members=3,duration_h=2,concentration_um=10))
    assert np.asarray(a['final_state'])[:,2].mean()>np.asarray(a['control_final_state'])[:,2].mean()
    assert a['epistemic_state']=='MODEL_ASSUMPTION'

@pytest.mark.parametrize('kwargs',[{'members':0},{'members':1.5},{'concentration_um':float('nan')},{'backend':'fake'},{'ec50_um':0}])
def test_invalid_configuration(kwargs):
    with pytest.raises((ValueError,TypeError)):run_simulation(RunConfig(**kwargs))

def test_cancellation():
    with pytest.raises(RunCancelled):run_simulation(RunConfig(members=1),cancelled=lambda:True)

def test_persistence_integrity(tmp_path):
    result=run_simulation(RunConfig(members=1,duration_h=1))
    store=RunStore(tmp_path);path=store.save(result)
    assert store.load_all()[0]['id']==result['id']
    from pathlib import Path
    Path(path).write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):store.load_all()

def test_mapping_rejects_wrong_model_and_preserves_species():
    service=StructureMappingService()
    assert service.map_to_biological(StructureResidueRef('1U19',2,'A',23)) is None
    assert service.map_to_biological(StructureResidueRef('1U19',1,'A',23,insertion_code='A')) is None
    ref=service.map_to_biological(StructureResidueRef('1U19',1,'B',23))
    assert ref.protein_id=='P02699' and ref.species=='Bos taurus'

def test_chemical_design_and_invalid_input():
    d=build_design('CCO');assert d['formula']=='C2H6O'
    assert d['activity_prediction'] is None and len(d['sdf'])>100
    with pytest.raises(ValueError):build_design('not a molecule')

def test_controller_commits_result_async(qtbot,tmp_path,monkeypatch):
    monkeypatch.setenv('VIRTUALLAB_DATA_DIR',str(tmp_path))
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from virtual_lab.gui.services.experiment_controller import ExperimentController
    ws=WorkspaceState();controller=ExperimentController(ws)
    with qtbot.waitSignal(controller.runFinished,timeout=15000):controller.run_experiment({'members':2,'duration_h':1})
    assert ws.current_result['status']=='completed'
    assert RunStore(tmp_path).load_all()[0]['id']==ws.current_result['id']
