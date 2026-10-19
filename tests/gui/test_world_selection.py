import pytest
from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.gui.services.selection import ScientificSelection, SelectionKind
from virtual_lab.gui.services.mapping import StructureMappingService, StructureResidueRef
from virtual_lab.gui.services.selection_controller import SelectionController
from virtual_lab.gui.services.evidence_store import EvidenceStore

def test_structure_residue_mapping():
    ws = WorkspaceState()
    mapping_service = StructureMappingService()
    controller = SelectionController(ws, mapping_service)
    
    # Simulate Mol* click on 1U19 Chain A Res 23
    controller.handle_structure_click("1U19", 1, "A", 23)
    
    # Should resolve to deposited bovine UniProt P02699, not human RHO
    assert ws.selected_object is not None
    assert ws.selected_object.kind == SelectionKind.RESIDUE
    assert ws.selected_object.protein_id == "P02699"
    assert ws.selected_object.residue_number == 23
    
def test_unmapped_structure_residue():
    ws = WorkspaceState()
    mapping_service = StructureMappingService()
    controller = SelectionController(ws, mapping_service)
    
    # Simulate Mol* click on an unmapped residue (e.g., 999)
    controller.handle_structure_click("1U19", 1, "A", 999)
    
    # Should resolve to UNKNOWN protein, showing unmapped
    assert ws.selected_object is not None
    assert ws.selected_object.kind == SelectionKind.RESIDUE
    assert ws.selected_object.protein_id == "UNKNOWN"
    assert ws.selected_object.residue_number == 999

def test_navigator_selection_updates_workspace():
    ws = WorkspaceState()
    mapping_service = StructureMappingService()
    controller = SelectionController(ws, mapping_service)
    
    controller.handle_navigator_click("P23H")
    
    assert ws.selected_object is not None
    assert ws.selected_object.kind == SelectionKind.RESIDUE
    assert ws.selected_object.protein_id == "RHO"
    assert ws.selected_object.residue_number == 23

def test_evidence_store_dynamic_count():
    store = EvidenceStore()
    
    p23h_selection = ScientificSelection(kind=SelectionKind.RESIDUE, protein_id="RHO", residue_number=23)
    other_selection = ScientificSelection(kind=SelectionKind.RESIDUE, protein_id="RHO", residue_number=99)
    
    assert store.count_for_selection(p23h_selection) == 3
    assert store.count_for_selection(other_selection) == 0

def test_shared_timeline_fires_events():
    ws = WorkspaceState()
    
    events = []
    ws.simulationTimeChanged.connect(lambda v: events.append(v))
    
    ws.simulation_time_h = 24.0
    
    assert events == [24.0]
    assert ws.simulation_time_h == 24.0
