from PySide6.QtCore import QObject,Signal,Slot
from virtual_lab.gui.services.selection import ScientificSelection,SelectionKind
from virtual_lab.gui.services.mapping import StructureResidueRef
class SelectionController(QObject):
    focusRequested=Signal(object)
    viewRequested=Signal(str)
    def __init__(self,workspace,mapping_service):
        super().__init__(workspace);self.workspace=workspace;self.mapping_service=mapping_service
    @Slot(str,int,str,int)
    def handle_structure_click(self,structure_id,model_id,chain_id,auth_residue_number,insertion_code=""):
        ref=StructureResidueRef(structure_id,model_id,chain_id,auth_residue_number,insertion_code=insertion_code)
        bio=self.mapping_service.map_to_biological(ref)
        self.workspace.selected_object=ScientificSelection(kind=SelectionKind.RESIDUE,
            protein_id=bio.protein_id if bio else 'UNKNOWN',residue_number=bio.canonical_position if bio else auth_residue_number,
            chain_id=chain_id,structure_id=structure_id,model_id=model_id,auth_residue_number=auth_residue_number,insertion_code=insertion_code)
    def handle_navigator_click(self,item_id):
        if item_id=='P23H':
            self.workspace.selected_object=ScientificSelection(kind=SelectionKind.RESIDUE,protein_id='RHO',residue_number=23)
            self.viewRequested.emit('Protein Context')
            # Focus the explicitly labeled bovine proxy without changing human selection.
            self.focusRequested.emit({'structure_id':'1U19','model_id':1,'chain_id':'A','auth_residue_number':23,'insertion_code':''})
        elif item_id in ('YC-001','YC-054'):
            self.workspace.selected_object=ScientificSelection(kind=SelectionKind.COMPOUND,compound_id=item_id)
            self.viewRequested.emit('Molecular')
        elif item_id in ('Molecular','Protein Context','Cellular','Tissue'):
            self.viewRequested.emit(item_id)
        elif item_id.startswith('parameter:'):
            self.workspace.selected_object=ScientificSelection(kind=SelectionKind.PARAMETER,parameter_id=item_id.split(':')[1])
        elif item_id=='Protein':
            self.workspace.selected_object=ScientificSelection(kind=SelectionKind.PROTEIN,protein_id='RHO')
            self.viewRequested.emit('Protein Context')
