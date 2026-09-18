import math
from typing import List, Tuple
from .models import HyperVoxel, EmbeddingMetadata
from .store import MemoryStore

class RetrievalEngine:
    def __init__(self, store: MemoryStore):
        self.store = store

    def retrieve_by_similarity(self, query_vector: List[float], query_metadata: EmbeddingMetadata, top_k: int = 5) -> List[Tuple[HyperVoxel, float]]:
        # This explicitly validates embedding metadata and does a mock deterministic retrieval (cosine similarity)
        voxels = self.store.get_all_voxels()
        
        results = []
        for v in voxels:
            if not v.embedding or not v.embedding_metadata:
                continue
                
            # Compatibility Gate
            if not query_metadata.is_compatible(v.embedding_metadata):
                raise ValueError(f"Incompatible embedding spaces: {query_metadata} vs {v.embedding_metadata}")
                
            # Compute cosine similarity
            dot = sum(a * b for a, b in zip(query_vector, v.embedding))
            norm_a = math.sqrt(sum(a * a for a in query_vector))
            norm_b = math.sqrt(sum(b * b for b in v.embedding))
            
            if norm_a == 0 or norm_b == 0:
                sim = 0.0
            else:
                sim = dot / (norm_a * norm_b)
                
            results.append((v, sim))
            
        # Tie-breaking for determinism: sort by sim DESC, then voxel_id ASC
        results.sort(key=lambda x: (-x[1], x[0].voxel_id))
        return results[:top_k]
