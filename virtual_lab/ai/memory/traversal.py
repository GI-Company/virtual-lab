from typing import List, Set, Dict, Tuple
from .models import HyperVoxel, HyperEdge
from .types import Scope, AuthoritativeResolutionState
from .store import MemoryStore
from .authoritative import AuthoritativeResolver

class GraphTraversal:
    def __init__(self, store: MemoryStore, resolver: AuthoritativeResolver):
        self.store = store
        self.resolver = resolver

    def traverse(
        self, 
        start_voxel_ids: List[str], 
        experiment_scope: str,
        max_hops: int = 3, 
        max_nodes: int = 50,
        allowed_relation_types: Set[str] = None
    ) -> Tuple[List[HyperVoxel], List[HyperEdge]]:
        """
        Traverses the graph outwards from the start nodes.
        Obeys strict limits on hops, max nodes, experiment scoping, and invalidity filters.
        """
        visited_voxels = set()
        visited_edges = set()
        
        result_voxels = []
        result_edges = []
        
        # Queue stores (voxel_id, current_hop)
        queue = [(vid, 0) for vid in start_voxel_ids]
        
        # Sort initial queue to ensure deterministic behavior
        queue.sort(key=lambda x: x[0])
        
        while queue and len(visited_voxels) < max_nodes:
            current_vid, current_hop = queue.pop(0)
            
            if current_vid in visited_voxels:
                continue
                
            voxel = self.store.get_voxel(current_vid)
            if not voxel:
                visited_voxels.add(current_vid)
                continue
                
            # Stale / Missing check
            state = self.resolver.resolve(voxel.authoritative_ref)
            if state in (AuthoritativeResolutionState.MISSING, AuthoritativeResolutionState.HASH_MISMATCH, AuthoritativeResolutionState.STALE):
                # We skip adding this to valid results
                visited_voxels.add(current_vid)
                continue
                
            visited_voxels.add(current_vid)
            result_voxels.append(voxel)
            
            if current_hop >= max_hops:
                continue
                
            edges = self.store.get_edges_for(current_vid)
            
            # Sort edges for deterministic traversal tie-breaking
            edges.sort(key=lambda e: e.edge_id)
            
            for edge in edges:
                if edge.edge_id in visited_edges:
                    continue
                    
                if allowed_relation_types and edge.relation_type not in allowed_relation_types:
                    continue
                    
                # Scoping enforcement
                if edge.scope == Scope.EXPERIMENT_LOCAL:
                    # Edge belongs strictly to one experiment. We check if both ends belong to the current scope.
                    # Actually, the edge itself has source/target.
                    # We check if the target voxel is in the current experiment scope.
                    target_vid = edge.target_voxel_id if edge.source_voxel_id == current_vid else edge.source_voxel_id
                    target_v = self.store.get_voxel(target_vid)
                    if target_v and target_v.authoritative_ref.experiment_id != experiment_scope:
                        continue # Reject cross-experiment leakage
                        
                elif edge.scope == Scope.CROSS_EXPERIMENT_EXPLICIT:
                    if not edge.cross_experiment_ids or experiment_scope not in edge.cross_experiment_ids:
                        continue # Explicitly not allowed for this experiment
                        
                visited_edges.add(edge.edge_id)
                result_edges.append(edge)
                
                next_vid = edge.target_voxel_id if edge.source_voxel_id == current_vid else edge.source_voxel_id
                if next_vid not in visited_voxels:
                    queue.append((next_vid, current_hop + 1))
                    
            # Re-sort queue for determinism if we appended new items
            queue.sort(key=lambda x: (x[1], x[0]))
            
        return result_voxels, result_edges
