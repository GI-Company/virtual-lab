import pytest
from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.gui.services.selection import ScientificSelection, SelectionKind

def test_workspace_state_signals():
    ws = WorkspaceState()
    
    # Test simulation time
    time_emitted = []
    ws.simulationTimeChanged.connect(lambda v: time_emitted.append(v))
    ws.simulation_time_h = 24.5
    assert time_emitted == [24.5]
    assert ws.simulation_time_h == 24.5
    
    # Test selection
    selection_emitted = []
    ws.selectedObjectChanged.connect(lambda v: selection_emitted.append(v))
    
    sel = ScientificSelection(
        kind=SelectionKind.RESIDUE,
        protein_id="RHO",
        chain_id="A",
        residue_number=23
    )
    ws.selected_object = sel
    
    assert len(selection_emitted) == 1
    assert selection_emitted[0].residue_number == 23
    assert ws.selected_object == sel
    
def test_experiment_change():
    ws = WorkspaceState()
    exp_emitted = []
    ws.activeExperimentChanged.connect(lambda v: exp_emitted.append(v))
    
    ws.active_experiment_id = "EXP-123"
    assert exp_emitted == ["EXP-123"]
    assert ws.active_experiment_id == "EXP-123"
