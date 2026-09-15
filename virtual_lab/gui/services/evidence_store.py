import json
from pathlib import Path
from virtual_lab.gui.services.selection import SelectionKind
class EvidenceStore:
    def __init__(self):
        self.records=json.loads((Path(__file__).parents[1]/'assets/evidence.json').read_text())['claims']
    def records_for_selection(self,selection):
        if selection is None:return self.records
        if selection.kind==SelectionKind.RESIDUE and selection.protein_id=='RHO' and selection.residue_number==23:
            return [r for r in self.records if r['id'] in ('variant_pathogenic','mechanism_misfolding','yc001_human_p23h_cellular')]
        if selection.kind==SelectionKind.COMPOUND and selection.compound_id=='YC-001':
            return [r for r in self.records if r['id'].startswith('yc001_') or r['id']=='p23h_preclinical_followup']
        if selection.kind==SelectionKind.PROTEIN and selection.protein_id=='RHO':
            return [r for r in self.records if r['id']=='target_identity']
        return []
    def count_for_selection(self,selection):return len(self.records_for_selection(selection))
