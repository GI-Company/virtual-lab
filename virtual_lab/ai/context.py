from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import hashlib
from ..core.ledger import canonicalJSON

class ScientificContext(BaseModel):
    context_id: str
    disease_model_id: str
    disease_model_hash: str
    experiment_id: str
    experiment_hash: str
    
    state_schema: List[str]
    state_constraints: Dict[str, Any]
    
    parameter_values: Dict[str, float]
    parameter_epistemics: Dict[str, str]
    parameter_uncertainties: Dict[str, float]
    
    exposure_model: str
    compound_identity: str
    
    evidence_snapshot_hash: str
    mechanism_graph_hash: str
    
    simulation_backend: str
    numerical_validation: str
    
    selected_results: Optional[Dict[str, Any]] = None

def generate_context_hash(context: ScientificContext) -> str:
    canonical_str = canonicalJSON(context.model_dump())
    return hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()
