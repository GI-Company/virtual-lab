from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Optional, Any
import hashlib
import json

class RecastingProfile(Enum):
    SEMANTIC = auto()
    MECHANISTIC = auto()
    EVIDENCE = auto()
    EXPERIMENT = auto()
    TEMPORAL = auto()
    CAUSAL_PATH = auto()
    CONFLICT = auto()

@dataclass
class AuthoritativeSnapshot:
    store_kind: str
    entity_type: str
    entity_id: str
    entity_version: Optional[str]
    content_hash: Optional[str]
    resolution_state: str
    epistemic_state: Optional[str]
    experiment_membership: Optional[str]

@dataclass
class RenderedNode:
    render_id: str
    voxel_id: str
    entity_id: str
    entity_type: str
    memory_class: str
    activation: float
    authoritative_resolution: str

@dataclass
class RenderedEdge:
    render_id: str
    source: str
    target: str
    relation_type: str

@dataclass
class SymbolicSidecar:
    view_id: str
    nodes: List[RenderedNode]
    edges: List[RenderedEdge]

@dataclass
class LayoutSpec:
    algorithm: str
    version: str
    seed: int
    temporal_basis: str

@dataclass
class BoundsSpec:
    max_nodes: int
    max_edges: int
    max_hops: int
    activation_threshold: float

@dataclass
class HVIEWContent:
    query: str
    profile: str
    focus_voxel_id: str
    experiment_scope: str
    memory_revision: str
    layout_spec: LayoutSpec
    activation_weight_set_id: str
    bounds: BoundsSpec
    nodes: List[Dict[str, Any]] # Raw voxel subset representations
    edges: List[Dict[str, Any]]
    authoritative_snapshot: List[AuthoritativeSnapshot]
    
    def canonical_serialize(self) -> str:
        # Custom deterministic serialization to ensure exact SHA-256 match
        # We sort dict keys natively.
        def to_dict(obj):
            if hasattr(obj, '__dict__'):
                return {k: to_dict(v) for k, v in vars(obj).items() if not k.startswith('_')}
            elif isinstance(obj, list):
                return [to_dict(i) for i in obj]
            elif isinstance(obj, dict):
                return {k: to_dict(v) for k, v in obj.items()}
            else:
                return obj
                
        d = to_dict(self)
        return json.dumps(d, sort_keys=True, separators=(',', ':'))

@dataclass
class HVIEWArtifact:
    view_id: str
    created_at_ns: int
    content: HVIEWContent
    view_sha256: str
