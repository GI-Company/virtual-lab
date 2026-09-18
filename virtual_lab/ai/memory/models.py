from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from .types import MemoryClass, TemporalBasis, Scope

@dataclass(frozen=True)
class AuthoritativeReference:
    store_kind: str
    entity_type: str
    entity_id: str
    entity_version: Optional[str] = None
    content_hash: Optional[str] = None
    experiment_id: Optional[str] = None

    @property
    def uniqueness_key(self) -> str:
        return f"{self.store_kind}::{self.entity_type}::{self.entity_id}::{self.entity_version or ''}"

@dataclass(frozen=True)
class EmbeddingMetadata:
    embedding_model_id: str
    embedding_dimension: int
    embedding_version: str

    def is_compatible(self, other: "EmbeddingMetadata") -> bool:
        if other is None:
            return False
        return (self.embedding_model_id == other.embedding_model_id and
                self.embedding_dimension == other.embedding_dimension and
                self.embedding_version == other.embedding_version)

@dataclass(frozen=True)
class SpatialProvenance:
    layout_algorithm: str
    layout_version: str
    layout_seed: int
    temporal_basis: TemporalBasis

@dataclass
class HyperVoxel:
    voxel_id: str
    memory_class: MemoryClass
    authoritative_ref: AuthoritativeReference
    
    # Optional index metadata
    embedding: Optional[List[float]] = None
    embedding_metadata: Optional[EmbeddingMetadata] = None
    
    # Cognitive / Spatial Derived (mutable only via specific cognitive paths)
    spatial_coords: Optional[tuple[float, float, float]] = None
    temporal_coord: Optional[float] = None
    spatial_provenance: Optional[SpatialProvenance] = None
    
    # Cognitive activation state
    cognitive_activation: float = 0.0
    access_count: int = 0
    last_accessed: float = 0.0
    
    # Short semantic label strictly for index readability/logging, NOT scientific payload
    semantic_label: Optional[str] = None

@dataclass
class HyperEdge:
    edge_id: str
    source_voxel_id: str
    target_voxel_id: str
    relation_type: str
    scope: Scope
    weight: float = 1.0
    
    # Cross-experiment pointers if applicable
    cross_experiment_ids: Optional[List[str]] = None
