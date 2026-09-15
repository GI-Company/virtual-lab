from dataclasses import dataclass
from pathlib import Path
from typing import Optional
@dataclass(frozen=True)
class StructureResidueRef:
    structure_id:str
    model_id:int
    chain_id:str
    auth_residue_number:int
    label_seq_id:Optional[int]=None
    insertion_code:str=""
@dataclass(frozen=True)
class BiologicalResidueRef:
    protein_id:str
    canonical_position:int
    wild_type:str
    mutation:Optional[str]=None
    species:str="Bos taurus"
class StructureMappingService:
    """Map only the deposited bovine chain numbering. No asserted human mapping."""
    def __init__(self):
        self.residues={}
        path=Path(__file__).parents[1]/'assets/1u19.pdb'
        if path.exists():
            for line in path.read_text().splitlines():
                if line.startswith('ATOM  '):
                    self.residues[(line[21],int(line[22:26]),line[26].strip())]=line[17:20].strip()
    def map_to_biological(self,ref):
        if ref.structure_id.upper()!='1U19' or ref.model_id!=1 or ref.insertion_code:return None
        # The PDB DBREF maps bovine UniProt OPSD_BOVIN/P02699 positions 1–348.
        key=(ref.chain_id,ref.auth_residue_number,ref.insertion_code)
        if key not in self.residues or not 1<=ref.auth_residue_number<=348:return None
        return BiologicalResidueRef('P02699',ref.auth_residue_number,self.residues[key])
