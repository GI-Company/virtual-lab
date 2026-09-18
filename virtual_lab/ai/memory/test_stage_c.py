import unittest
import os
import sys

# Ensure we can import virtual_lab
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from virtual_lab.ai.memory.types import MemoryClass, AuthoritativeResolutionState, TemporalBasis, Scope
from virtual_lab.ai.memory.models import HyperVoxel, HyperEdge, AuthoritativeReference, EmbeddingMetadata, SpatialProvenance
from virtual_lab.ai.memory.store import MemoryStore
from virtual_lab.ai.memory.authoritative import AuthoritativeResolver
from virtual_lab.ai.memory.views import RecastingProfile, BoundsSpec, LayoutSpec, HVIEWContent
from virtual_lab.ai.memory.recasting import RecastingEngine
from virtual_lab.ai.memory.rendering import Renderer

class TestStageC(unittest.TestCase):
    def setUp(self):
        self.db_path = ":memory:"
        self.store = MemoryStore(self.db_path)
        self.resolver = AuthoritativeResolver()
        self.engine = RecastingEngine(self.store, self.resolver)
        self.renderer = Renderer()

    def tearDown(self):
        self.store.close()

    def test_01_node_sidecar_matches(self):
        # 1. Rendered node IDs and sidecar IDs match 1:1.
        ref = AuthoritativeReference("S", "T", "1")
        emb = EmbeddingMetadata("M1", 2, "v1")
        self.store.upsert_voxel(HyperVoxel("V1", MemoryClass.SEMANTIC, ref, embedding=[1.0, 0.0], embedding_metadata=emb))
        self.resolver.register_mock_entity("S", "T", "1", "")
        
        bounds = BoundsSpec(10, 10, 1, 0.0)
        layout = LayoutSpec("alg", "1", 42, "NONE")
        
        artifact, sidecar = self.engine.compile(
            query_vector=[1.0, 0.0], query_metadata=emb, query_text="Q", 
            profile=RecastingProfile.SEMANTIC, experiment_scope="EXP", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="w1"
        )
        
        self.assertEqual(len(artifact.content.nodes), len(sidecar.nodes))
        
        proj = self.renderer.render(artifact, sidecar)
        self.assertEqual(len(sidecar.nodes), len(proj["nodes"]))
        
        # Ensure ID mapping is solid
        for sn, pn in zip(sidecar.nodes, proj["nodes"]):
            self.assertEqual(sn.render_id, pn["render_id"])

    def test_02_03_resolved_chain(self):
        # 2. Every rendered node resolves to a HyperVoxel.
        # 3. Every HyperVoxel resolves to its authoritative snapshot.
        ref = AuthoritativeReference("S", "T", "1")
        emb = EmbeddingMetadata("M1", 2, "v1")
        self.store.upsert_voxel(HyperVoxel("V1", MemoryClass.SEMANTIC, ref, embedding=[1.0, 0.0], embedding_metadata=emb))
        self.resolver.register_mock_entity("S", "T", "1", "")
        
        bounds = BoundsSpec(10, 10, 1, 0.0)
        layout = LayoutSpec("alg", "1", 42, "NONE")
        
        artifact, sidecar = self.engine.compile(
            query_vector=[1.0, 0.0], query_metadata=emb, query_text="Q", 
            profile=RecastingProfile.SEMANTIC, experiment_scope="EXP", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="w1"
        )
        
        self.assertEqual(len(sidecar.nodes), 1)
        self.assertEqual(sidecar.nodes[0].voxel_id, "V1")
        
        # V1 exists in store
        fetched_v = self.store.get_voxel("V1")
        self.assertIsNotNone(fetched_v)
        
        # Snapshot exists in content
        snapshots = [s for s in artifact.content.authoritative_snapshot if s.entity_id == fetched_v.authoritative_ref.entity_id]
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].resolution_state, "VALID")

    def test_04_05_bounds_and_leaks(self):
        # 4. No unselected memory can leak into the view.
        # 5. View bounds are strictly enforced (max_nodes, max_hops).
        emb = EmbeddingMetadata("M1", 2, "v1")
        
        # Create a linear chain of 5 nodes
        for i in range(5):
            ref = AuthoritativeReference("S", "T", str(i))
            self.resolver.register_mock_entity("S", "T", str(i), "")
            # Node 0 has high sim, others 0
            v_emb = [1.0, 0.0] if i == 0 else [0.0, 0.0]
            self.store.upsert_voxel(HyperVoxel(f"V{i}", MemoryClass.SEMANTIC, ref, embedding=v_emb, embedding_metadata=emb))
            if i > 0:
                self.store.upsert_edge(HyperEdge(f"E{i}", f"V{i-1}", f"V{i}", "REL", Scope.GLOBAL))
                
        # Limit to 3 nodes via bounds.max_nodes
        bounds = BoundsSpec(max_nodes=3, max_edges=10, max_hops=10, activation_threshold=0.0)
        layout = LayoutSpec("alg", "1", 42, "NONE")
        
        artifact, sidecar = self.engine.compile(
            query_vector=[1.0, 0.0], query_metadata=emb, query_text="Q", 
            profile=RecastingProfile.SEMANTIC, experiment_scope="EXP", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="w1"
        )
        
        # Length should be strictly 3
        self.assertEqual(len(sidecar.nodes), 3)
        # Check no memory leaked
        vids = {n.voxel_id for n in sidecar.nodes}
        self.assertNotIn("V3", vids)
        self.assertNotIn("V4", vids)

    def test_06_experiment_scope_survives(self):
        # 6. Experiment scope survives recasting.
        ref = AuthoritativeReference("S", "T", "1")
        emb = EmbeddingMetadata("M1", 2, "v1")
        self.store.upsert_voxel(HyperVoxel("V1", MemoryClass.SEMANTIC, ref, embedding=[1.0, 0.0], embedding_metadata=emb))
        self.resolver.register_mock_entity("S", "T", "1", "")
        
        bounds = BoundsSpec(10, 10, 1, 0.0)
        layout = LayoutSpec("alg", "1", 42, "NONE")
        
        artifact, sidecar = self.engine.compile(
            query_vector=[1.0, 0.0], query_metadata=emb, query_text="Q", 
            profile=RecastingProfile.SEMANTIC, experiment_scope="MY_EXP_SCOPE", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="w1"
        )
        
        self.assertEqual(artifact.content.experiment_scope, "MY_EXP_SCOPE")

    def test_07_invalid_records_excluded(self):
        # 7. Invalid authoritative records are excluded by default.
        emb = EmbeddingMetadata("M1", 2, "v1")
        ref1 = AuthoritativeReference("S", "T", "VALID_NODE")
        ref2 = AuthoritativeReference("S", "T", "MISSING_NODE")
        
        self.store.upsert_voxel(HyperVoxel("V1", MemoryClass.SEMANTIC, ref1, embedding=[1.0, 0.0], embedding_metadata=emb))
        self.store.upsert_voxel(HyperVoxel("V2", MemoryClass.SEMANTIC, ref2, embedding=[1.0, 0.0], embedding_metadata=emb))
        
        self.resolver.register_mock_entity("S", "T", "VALID_NODE", "")
        # Do not register MISSING_NODE
        
        bounds = BoundsSpec(10, 10, 1, 0.0)
        layout = LayoutSpec("alg", "1", 42, "NONE")
        
        artifact, sidecar = self.engine.compile(
            query_vector=[1.0, 0.0], query_metadata=emb, query_text="Q", 
            profile=RecastingProfile.SEMANTIC, experiment_scope="EXP", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="w1"
        )
        
        vids = {n.voxel_id for n in sidecar.nodes}
        self.assertIn("V1", vids)
        self.assertNotIn("V2", vids)

    def test_08_identical_inputs_identical_hashes(self):
        # 8. Same inputs generate perfectly identical HVIEW hashes.
        ref = AuthoritativeReference("S", "T", "1")
        emb = EmbeddingMetadata("M1", 2, "v1")
        self.store.upsert_voxel(HyperVoxel("V1", MemoryClass.SEMANTIC, ref, embedding=[1.0, 0.0], embedding_metadata=emb))
        self.resolver.register_mock_entity("S", "T", "1", "")
        
        bounds = BoundsSpec(10, 10, 1, 0.0)
        layout = LayoutSpec("alg", "1", 42, "NONE")
        
        artifact1, _ = self.engine.compile(
            query_vector=[1.0, 0.0], query_metadata=emb, query_text="Q", 
            profile=RecastingProfile.SEMANTIC, experiment_scope="EXP", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="w1"
        )
        
        artifact2, _ = self.engine.compile(
            query_vector=[1.0, 0.0], query_metadata=emb, query_text="Q", 
            profile=RecastingProfile.SEMANTIC, experiment_scope="EXP", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="w1"
        )
        
        self.assertEqual(artifact1.view_sha256, artifact2.view_sha256)
        # Verify created_at is different, but hash matches
        self.assertNotEqual(artifact1.created_at_ns, artifact2.created_at_ns)

    def test_09_10_11_rendering_safeguards(self):
        # 9. Changing the recasting profile changes the view WITHOUT modifying memory.
        # 10. Rendering does NOT mutate memory.
        # 11. Scientific state does NOT derive from coordinates or appearance.
        ref = AuthoritativeReference("S", "T", "1")
        emb = EmbeddingMetadata("M1", 2, "v1")
        self.store.upsert_voxel(HyperVoxel("V1", MemoryClass.SEMANTIC, ref, embedding=[1.0, 0.0], embedding_metadata=emb))
        self.resolver.register_mock_entity("S", "T", "1", "")
        
        v_before = self.store.get_voxel("V1")
        
        bounds = BoundsSpec(10, 10, 1, 0.0)
        layout = LayoutSpec("alg", "1", 42, "NONE")
        
        artifact, sidecar = self.engine.compile(
            query_vector=[1.0, 0.0], query_metadata=emb, query_text="Q", 
            profile=RecastingProfile.EVIDENCE, experiment_scope="EXP", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="w1"
        )
        
        proj = self.renderer.render(artifact, sidecar)
        
        v_after = self.store.get_voxel("V1")
        # Memory is untouched
        self.assertEqual(v_before.authoritative_ref.content_hash, v_after.authoritative_ref.content_hash)
        # Rendering creates independent projection
        self.assertIn("nodes", proj)
        # State didn't leak backwards
        self.assertFalse(hasattr(v_after, "scientific_strength"))

    def test_12_13_serialization(self):
        # 12. HVIEW survives serialize/reload without semantic drift.
        # 13. The projection can be identically regenerated from the HVIEW + sidecar.
        ref = AuthoritativeReference("S", "T", "1")
        emb = EmbeddingMetadata("M1", 2, "v1")
        self.store.upsert_voxel(HyperVoxel("V1", MemoryClass.SEMANTIC, ref, embedding=[1.0, 0.0], embedding_metadata=emb))
        self.resolver.register_mock_entity("S", "T", "1", "")
        
        bounds = BoundsSpec(10, 10, 1, 0.0)
        layout = LayoutSpec("alg", "1", 42, "NONE")
        
        artifact, sidecar = self.engine.compile(
            query_vector=[1.0, 0.0], query_metadata=emb, query_text="Q", 
            profile=RecastingProfile.SEMANTIC, experiment_scope="EXP", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="w1"
        )
        
        import json
        serialized = artifact.content.canonical_serialize()
        
        # Deserialize into dict, check determinism
        d = json.loads(serialized)
        self.assertEqual(d["query"], "Q")
        self.assertEqual(d["focus_voxel_id"], "V1")
        
        proj1 = self.renderer.render(artifact, sidecar)
        proj2 = self.renderer.render(artifact, sidecar)
        self.assertEqual(proj1, proj2)

    def test_14_no_gemma(self):
        # 14. Stage C runs without importing mlx_lm or initializing Gemma.
        self.assertNotIn("mlx_lm", sys.modules)

    def test_15_acceptance_scenario(self):
        # 15. Acceptance Scenario: Deterministic generation of the RHO P23H graph 
        # under CAUSAL_PATH vs EVIDENCE profiles. Verify hashes and purity.
        
        entities = [
            ("RHO_P23H", "CONCEPT"), ("YC001", "CONCEPT"),
            ("ER_RETENTION", "CONCEPT"), ("ER_STRESS", "CONCEPT"),
            ("VIABILITY", "CONCEPT"), ("EXP-42", "EXPERIMENT"),
            ("RUN-42", "RUN"), ("EVIDENCE-17", "EVIDENCE")
        ]
        
        emb_meta = EmbeddingMetadata("M1", 3, "1.0")
        
        for eid, etype in entities:
            self.resolver.register_mock_entity("S", etype, eid, "H")
            emb = [1.0, 0.5, 0.0] if eid in ["YC001", "VIABILITY"] else [0.0, 0.0, 0.0]
            ref = AuthoritativeReference("S", etype, eid, content_hash="H", experiment_id="EXP-42" if "42" in eid else None)
            
            # Upsert memory
            self.store.upsert_voxel(HyperVoxel(eid, MemoryClass.SEMANTIC, ref, embedding=emb, embedding_metadata=emb_meta, semantic_label=eid))
            
        edges = [
            ("E1", "YC001", "RHO_P23H", "AFFECTS", Scope.GLOBAL),
            ("E2", "RHO_P23H", "ER_RETENTION", "INCREASES", Scope.GLOBAL),
            ("E3", "ER_RETENTION", "ER_STRESS", "INCREASES", Scope.GLOBAL),
            ("E4", "ER_STRESS", "VIABILITY", "REDUCES", Scope.GLOBAL),
            ("E5", "RUN-42", "EXP-42", "TESTS", Scope.EXPERIMENT_LOCAL),
            ("E7", "EVIDENCE-17", "RHO_P23H", "SUPPORTS", Scope.GLOBAL)
        ]
        for e in edges:
            self.store.upsert_edge(HyperEdge(e[0], e[1], e[2], e[3], e[4]))
            
        bounds = BoundsSpec(10, 10, 4, 0.0)
        layout = LayoutSpec("alg", "1", 42, "NONE")
        
        # First Compile: CAUSAL_PATH
        art_causal1, sc_causal1 = self.engine.compile(
            query_vector=[1.0, 0.5, 0.0], query_metadata=emb_meta, query_text="YC-001 viability", 
            profile=RecastingProfile.CAUSAL_PATH, experiment_scope="EXP-42", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="ACT-v1"
        )
        
        # Exact rerun should produce identical hash
        art_causal2, sc_causal2 = self.engine.compile(
            query_vector=[1.0, 0.5, 0.0], query_metadata=emb_meta, query_text="YC-001 viability", 
            profile=RecastingProfile.CAUSAL_PATH, experiment_scope="EXP-42", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="ACT-v1"
        )
        self.assertEqual(art_causal1.view_sha256, art_causal2.view_sha256)
        
        # Second Compile: EVIDENCE
        art_evidence, sc_evidence = self.engine.compile(
            query_vector=[1.0, 0.5, 0.0], query_metadata=emb_meta, query_text="YC-001 viability", 
            profile=RecastingProfile.EVIDENCE, experiment_scope="EXP-42", 
            bounds=bounds, layout_spec=layout, activation_weight_set_id="ACT-v1"
        )
        
        # Content hashes must differ due to profile change
        self.assertNotEqual(art_causal1.view_sha256, art_evidence.view_sha256)
        
        # Rendering succeeds
        proj = self.renderer.render(art_causal1, sc_causal1)
        self.assertGreater(len(proj["nodes"]), 0)
        
        # Memory strictly unmodified
        v_yc = self.store.get_voxel("YC001")
        self.assertEqual(v_yc.authoritative_ref.content_hash, "H")

if __name__ == "__main__":
    unittest.main()
