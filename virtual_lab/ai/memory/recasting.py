from typing import List, Dict, Set, Any, Tuple
import hashlib
import time

from .store import MemoryStore
from .models import HyperVoxel, HyperEdge, EmbeddingMetadata
from .types import AuthoritativeResolutionState
from .retrieval import RetrievalEngine
from .traversal import GraphTraversal
from .authoritative import AuthoritativeResolver
from .spatial import LayoutGenerator
from .views import (
    RecastingProfile, BoundsSpec, LayoutSpec, 
    HVIEWContent, HVIEWArtifact, SymbolicSidecar, 
    AuthoritativeSnapshot, RenderedNode, RenderedEdge
)

class RecastingEngine:
    def __init__(self, store: MemoryStore, resolver: AuthoritativeResolver):
        self.store = store
        self.resolver = resolver
        self.retrieval_engine = RetrievalEngine(store)
        self.traversal_engine = GraphTraversal(store, resolver)

    def compile(
        self,
        query_vector: List[float],
        query_metadata: EmbeddingMetadata,
        query_text: str,
        profile: RecastingProfile,
        experiment_scope: str,
        bounds: BoundsSpec,
        layout_spec: LayoutSpec,
        activation_weight_set_id: str
    ) -> Tuple[HVIEWArtifact, SymbolicSidecar]:
        
        # 1. Capture memory revision + compile parameters
        start_revision = self.store.current_revision()

        # 2. RetrievalEngine for bounded seed voxels
        # For determinism, say we fetch top 5 seeds
        seeds = self.retrieval_engine.retrieve_by_similarity(query_vector, query_metadata, top_k=5)
        seed_ids = [s[0].voxel_id for s in seeds]
        
        if not seed_ids:
            # Handle empty query gracefully
            focus_voxel_id = ""
        else:
            focus_voxel_id = seed_ids[0]

        # 3. Bounded traversal
        # We enforce candidate bounds during traversal
        candidate_voxels, candidate_edges = self.traversal_engine.traverse(
            start_voxel_ids=seed_ids,
            experiment_scope=experiment_scope,
            max_hops=bounds.max_hops,
            max_nodes=bounds.max_nodes * 2 # Candidate ceiling
        )

        # 4. Authoritative resolution / filtering
        valid_voxels = []
        snapshots = []
        for v in candidate_voxels:
            state = self.resolver.resolve(v.authoritative_ref)
            if state in (
                AuthoritativeResolutionState.MISSING, 
                AuthoritativeResolutionState.HASH_MISMATCH,
                AuthoritativeResolutionState.STORE_UNAVAILABLE
            ):
                continue
                
            if state == AuthoritativeResolutionState.STALE and profile != RecastingProfile.CONFLICT:
                continue

            valid_voxels.append(v)
            snapshots.append(AuthoritativeSnapshot(
                store_kind=v.authoritative_ref.store_kind,
                entity_type=v.authoritative_ref.entity_type,
                entity_id=v.authoritative_ref.entity_id,
                entity_version=v.authoritative_ref.entity_version,
                content_hash=v.authoritative_ref.content_hash,
                resolution_state=state.name,
                epistemic_state=None, # In a real implementation this comes from resolver
                experiment_membership=v.authoritative_ref.experiment_id
            ))

        # 5. Recasting-profile filtering
        # e.g., if CAUSAL_PATH, we only keep certain edge types or memory classes
        # Simplified: we keep everything for this deterministic skeleton.
        filtered_voxels = valid_voxels
        
        # Filter edges to only include those between filtered_voxels
        v_ids = {v.voxel_id for v in filtered_voxels}
        filtered_edges = [e for e in candidate_edges if e.source_voxel_id in v_ids and e.target_voxel_id in v_ids]

        # 6. Activation / ranking
        # In a real system, calculate scores. Here we mock it or use existing cognitive_activation.
        # 7. Deterministic final node/edge pruning
        # Sort by activation DESC, then voxel_id ASC
        filtered_voxels.sort(key=lambda v: (-v.cognitive_activation, v.voxel_id))
        
        # Apply threshold and max_nodes
        final_voxels = [v for v in filtered_voxels if v.cognitive_activation >= bounds.activation_threshold][:bounds.max_nodes]
        final_v_ids = {v.voxel_id for v in final_voxels}
        
        # Prune edges
        final_edges = [e for e in filtered_edges if e.source_voxel_id in final_v_ids and e.target_voxel_id in final_v_ids]
        final_edges.sort(key=lambda e: e.edge_id)
        final_edges = final_edges[:bounds.max_edges]

        # Re-sort final voxels for deterministic serialization
        final_voxels.sort(key=lambda v: v.voxel_id)

        # Ensure revision hasn't drifted
        end_revision = self.store.current_revision()
        if start_revision != end_revision:
            raise RuntimeError(f"Memory revision drifted during compilation from {start_revision} to {end_revision}. Aborting.")

        # 8. Deterministic spatial mapping on frozen graph
        mapper = LayoutGenerator(
            algorithm=layout_spec.algorithm, 
            version=layout_spec.version, 
            seed=layout_spec.seed
        )
        for idx, v in enumerate(final_voxels):
            mapper.compute_spatial_coordinates(v, depth=0, index=idx)

        # 9/10. Generate Canonical HVIEWContent
        voxel_dicts = []
        for v in final_voxels:
            d = {
                "voxel_id": v.voxel_id,
                "memory_class": v.memory_class.name,
                "authoritative_ref": {
                    "store_kind": v.authoritative_ref.store_kind,
                    "entity_type": v.authoritative_ref.entity_type,
                    "entity_id": v.authoritative_ref.entity_id,
                },
                "spatial_coords": v.spatial_coords,
                "cognitive_activation": v.cognitive_activation,
                "semantic_label": v.semantic_label
            }
            voxel_dicts.append(d)
            
        edge_dicts = []
        for e in final_edges:
            d = {
                "edge_id": e.edge_id,
                "source": e.source_voxel_id,
                "target": e.target_voxel_id,
                "relation_type": e.relation_type,
                "weight": e.weight
            }
            edge_dicts.append(d)
            
        # Filter snapshots to only final voxels
        final_snapshots = [s for s in snapshots if s.entity_id in {v.authoritative_ref.entity_id for v in final_voxels}]
        final_snapshots.sort(key=lambda s: s.entity_id)

        content = HVIEWContent(
            query=query_text,
            profile=profile.name,
            focus_voxel_id=focus_voxel_id,
            experiment_scope=experiment_scope,
            memory_revision=start_revision,
            layout_spec=layout_spec,
            activation_weight_set_id=activation_weight_set_id,
            bounds=bounds,
            nodes=voxel_dicts,
            edges=edge_dicts,
            authoritative_snapshot=final_snapshots
        )

        # 11. Generate SHA-256 hash over canonical serialization
        serialized = content.canonical_serialize()
        view_sha256 = hashlib.sha256(serialized.encode('utf-8')).hexdigest()

        # 12. Assemble HVIEWArtifact
        view_id = f"HVIEW-{view_sha256[:12]}"
        created_at_ns = time.time_ns()
        
        artifact = HVIEWArtifact(
            view_id=view_id,
            created_at_ns=created_at_ns,
            content=content,
            view_sha256=view_sha256
        )

        # 13. Derive SymbolicSidecar strictly from completed HVIEWArtifact
        sidecar_nodes = []
        for i, n_dict in enumerate(artifact.content.nodes):
            sn = RenderedNode(
                render_id=f"N{i}",
                voxel_id=n_dict["voxel_id"],
                entity_id=n_dict["authoritative_ref"]["entity_id"],
                entity_type=n_dict["authoritative_ref"]["entity_type"],
                memory_class=n_dict["memory_class"],
                activation=n_dict["cognitive_activation"],
                authoritative_resolution="VALID" # Approximated for deterministic sidecar mapping
            )
            sidecar_nodes.append(sn)
            
        # Map voxel_id to render_id
        vid_to_rid = {sn.voxel_id: sn.render_id for sn in sidecar_nodes}
        
        sidecar_edges = []
        for i, e_dict in enumerate(artifact.content.edges):
            se = RenderedEdge(
                render_id=f"E{i}",
                source=vid_to_rid[e_dict["source"]],
                target=vid_to_rid[e_dict["target"]],
                relation_type=e_dict["relation_type"]
            )
            sidecar_edges.append(se)
            
        sidecar = SymbolicSidecar(
            view_id=artifact.view_id,
            nodes=sidecar_nodes,
            edges=sidecar_edges
        )

        return artifact, sidecar
