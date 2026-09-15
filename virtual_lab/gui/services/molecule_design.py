import hashlib,json
from rdkit import Chem
from rdkit.Chem import AllChem,Descriptors,rdMolDescriptors,rdFingerprintGenerator
from rdkit import DataStructs
from pathlib import Path

def build_design(smiles,seed=42):
    if len(smiles)>1000:raise ValueError('SMILES is too long')
    mol=Chem.MolFromSmiles(smiles)
    if mol is None:raise ValueError('Invalid SMILES; correct the chemical structure before generating')
    if not 1<=mol.GetNumHeavyAtoms()<=80 or rdMolDescriptors.CalcNumRotatableBonds(mol)>20:
        raise ValueError('Interactive conformers support 1–80 heavy atoms and at most 20 rotatable bonds')
    if len(Chem.GetMolFrags(mol))!=1:raise ValueError('Use one connected molecule; salts and mixtures need explicit preparation')
    canonical=Chem.MolToSmiles(mol,isomericSmiles=True)
    h=Chem.AddHs(mol);params=AllChem.ETKDGv3();params.randomSeed=int(seed);params.maxIterations=100
    if AllChem.EmbedMolecule(h,params)<0:raise ValueError('Could not generate a conformer')
    if not AllChem.UFFHasAllMoleculeParams(h):raise ValueError('UFF does not support all atoms in this molecule')
    status=AllChem.UFFOptimizeMolecule(h,maxIters=300)
    generator=rdFingerprintGenerator.GetMorganGenerator(radius=2,fpSize=2048)
    fingerprint=generator.GetFingerprint(mol);neighbors=[]
    for record in json.loads((Path(__file__).parents[1]/'assets/compounds.json').read_text()):
        if record['identity_status']!='model_eligible' or not record['smiles']:continue
        candidate=Chem.MolFromSmiles(record['smiles'])
        if candidate is None:continue
        similarity=DataStructs.TanimotoSimilarity(fingerprint,generator.GetFingerprint(candidate))
        neighbors.append({'compound':record['compound_name'],'similarity':similarity})
    return {'schema_version':1,'canonical_smiles':canonical,'formula':rdMolDescriptors.CalcMolFormula(mol),
        'molecular_weight':Descriptors.MolWt(mol),'logp':Descriptors.MolLogP(mol),'tpsa':Descriptors.TPSA(mol),
        'hbd':rdMolDescriptors.CalcNumHBD(mol),'hba':rdMolDescriptors.CalcNumHBA(mol),
        'seed':seed,'uff_converged':status==0,'sdf':Chem.MolToMolBlock(h)+'\n$$$$\n',
        'neighbors':sorted(neighbors,key=lambda x:x['similarity'],reverse=True)[:5],
        'epistemic_state':'COMPUTED_GEOMETRY','activity_prediction':None,
        'limitations':'Single generated conformer; no docking, pharmacology, toxicity, or efficacy prediction.'}
