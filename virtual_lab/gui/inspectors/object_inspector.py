from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton
from virtual_lab.gui.services.selection import ScientificSelection,SelectionKind
from virtual_lab.diseases.rho_p23h.model import RhoP23HModel
class InspectorRegistry:
    def __init__(self):self.renderers={}
    def register(self,kind,renderer):self.renderers[kind]=renderer
    def renderer_for(self,selection,workspace,store):
        return self.renderers.get(selection.kind,render_generic)(selection,workspace,store)

def render_generic(selection,workspace,store):
    panel=QWidget();layout=QVBoxLayout(panel)
    def text(value):
        label=QLabel(value);label.setWordWrap(True);layout.addWidget(label)
    if selection.kind==SelectionKind.NONE:text('Select a residue, compound, or model parameter.')
    elif selection.kind==SelectionKind.RESIDUE:
        if selection.protein_id=='RHO' and selection.residue_number==23:
            text('Human RHO • P23H');text('Curated human variant: proline → histidine at position 23. The scene focuses bovine wild-type Pro23 as a structural reference; it is not a human mutant structure.')
            for name in ('k_mis','k_traffic','k_ERAD'):
                button=QPushButton(name);button.clicked.connect(lambda checked=False,n=name:setattr(workspace,'selected_object',ScientificSelection(kind=SelectionKind.PARAMETER,parameter_id=n)));layout.addWidget(button)
        else:
            text(f"{selection.structure_id} • model {selection.model_id} • chain {selection.chain_id} • residue {selection.auth_residue_number}{selection.insertion_code}")
            text('Bos taurus rhodopsin • UniProt P02699. Human mapping unresolved.' if selection.protein_id=='P02699' else 'MAPPING UNRESOLVED')
    elif selection.kind==SelectionKind.PARAMETER:
        p=RhoP23HModel().parameters().get(selection.parameter_id)
        text(selection.parameter_id or '')
        if p:text(f"Model default: {p.value} {p.unit}. Treat as an assumption in this experiment; independent calibration is unavailable here.")
    elif selection.kind==SelectionKind.COMPOUND:
        text(selection.compound_id or 'Compound')
        text('Source-linked preclinical evidence is available below. Experiment response settings remain explicitly assumed.' if selection.compound_id=='YC-001' else 'No linked activity evidence in this local collection. Do not inherit YC-001 activity.')
    else:text(selection.protein_id or selection.kind.name)
    n=store.count_for_selection(selection)
    button=QPushButton(f'View Evidence ({n})');button.clicked.connect(lambda:workspace.evidenceSelectionChanged.emit(selection));layout.addWidget(button)
    layout.addStretch();return panel

class ObjectInspector(QWidget):
    def __init__(self,workspace,evidence_store,parent=None):
        super().__init__(parent);self.workspace=workspace;self.store=evidence_store;self.registry=InspectorRegistry()
        for kind in SelectionKind:self.registry.register(kind,render_generic)
        self.layout=QVBoxLayout(self);self.current_renderer=None
        workspace.selectedObjectChanged.connect(self._on_selection_changed);self._on_selection_changed(workspace.selected_object)
    def _on_selection_changed(self,selection):
        if self.current_renderer:self.layout.removeWidget(self.current_renderer);self.current_renderer.deleteLater()
        self.current_renderer=self.registry.renderer_for(selection,self.workspace,self.store);self.layout.addWidget(self.current_renderer)
