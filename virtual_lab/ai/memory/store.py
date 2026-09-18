import sqlite3
import json
from typing import List, Optional, Dict, Any

from .types import MemoryClass, Scope, TemporalBasis
from .models import HyperVoxel, HyperEdge, AuthoritativeReference, EmbeddingMetadata, SpatialProvenance

class MemoryStore:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        # Use WAL mode
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        
        # Voxels table
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS voxels (
            voxel_id TEXT PRIMARY KEY,
            memory_class TEXT NOT NULL,
            
            -- Authoritative Reference
            store_kind TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            entity_version TEXT,
            content_hash TEXT,
            experiment_id TEXT,
            
            -- Embeddings
            embedding JSON,
            embedding_model_id TEXT,
            embedding_dimension INTEGER,
            embedding_version TEXT,
            
            -- Spatial
            spatial_coords JSON,
            temporal_coord REAL,
            layout_algorithm TEXT,
            layout_version TEXT,
            layout_seed INTEGER,
            temporal_basis TEXT,
            
            -- Cognitive
            cognitive_activation REAL DEFAULT 0.0,
            access_count INTEGER DEFAULT 0,
            last_accessed REAL DEFAULT 0.0,
            semantic_label TEXT,
            
            UNIQUE(store_kind, entity_type, entity_id, entity_version)
        )
        """)
        
        # Edges table
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            edge_id TEXT PRIMARY KEY,
            source_voxel_id TEXT NOT NULL,
            target_voxel_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            scope TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            cross_experiment_ids JSON,
            
            FOREIGN KEY(source_voxel_id) REFERENCES voxels(voxel_id) ON DELETE CASCADE,
            FOREIGN KEY(target_voxel_id) REFERENCES voxels(voxel_id) ON DELETE CASCADE
        )
        """)
        
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_source ON edges(source_voxel_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_target ON edges(target_voxel_id)")
        
        # Migration metadata table
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_info (
            version INTEGER PRIMARY KEY,
            memory_revision INTEGER DEFAULT 0
        )
        """)
        self.conn.execute("INSERT OR IGNORE INTO schema_info (version, memory_revision) VALUES (1, 0)")
        self.conn.commit()

    def current_revision(self) -> str:
        row = self.conn.execute("SELECT memory_revision FROM schema_info WHERE version = 1").fetchone()
        return str(row["memory_revision"]) if row else "0"

    def _increment_revision(self):
        self.conn.execute("UPDATE schema_info SET memory_revision = memory_revision + 1 WHERE version = 1")

    def close(self):
        self.conn.close()

    def upsert_voxel(self, voxel: HyperVoxel):
        auth = voxel.authoritative_ref
        emb_meta = voxel.embedding_metadata
        sp_meta = voxel.spatial_provenance
        
        self.conn.execute("""
        INSERT INTO voxels (
            voxel_id, memory_class,
            store_kind, entity_type, entity_id, entity_version, content_hash, experiment_id,
            embedding, embedding_model_id, embedding_dimension, embedding_version,
            spatial_coords, temporal_coord, layout_algorithm, layout_version, layout_seed, temporal_basis,
            cognitive_activation, access_count, last_accessed, semantic_label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(voxel_id) DO UPDATE SET
            cognitive_activation=excluded.cognitive_activation,
            access_count=excluded.access_count,
            last_accessed=excluded.last_accessed,
            spatial_coords=excluded.spatial_coords,
            temporal_coord=excluded.temporal_coord,
            layout_algorithm=excluded.layout_algorithm,
            layout_version=excluded.layout_version,
            layout_seed=excluded.layout_seed,
            temporal_basis=excluded.temporal_basis,
            semantic_label=excluded.semantic_label
        """, (
            voxel.voxel_id, voxel.memory_class.name,
            auth.store_kind, auth.entity_type, auth.entity_id, auth.entity_version, auth.content_hash, auth.experiment_id,
            json.dumps(voxel.embedding) if voxel.embedding else None,
            emb_meta.embedding_model_id if emb_meta else None,
            emb_meta.embedding_dimension if emb_meta else None,
            emb_meta.embedding_version if emb_meta else None,
            json.dumps(voxel.spatial_coords) if voxel.spatial_coords else None,
            voxel.temporal_coord,
            sp_meta.layout_algorithm if sp_meta else None,
            sp_meta.layout_version if sp_meta else None,
            sp_meta.layout_seed if sp_meta else None,
            sp_meta.temporal_basis.name if sp_meta else None,
            voxel.cognitive_activation, voxel.access_count, voxel.last_accessed, voxel.semantic_label
        ))
        self.conn.commit()
        self._increment_revision()

    def upsert_edge(self, edge: HyperEdge):
        self.conn.execute("""
        INSERT OR REPLACE INTO edges (
            edge_id, source_voxel_id, target_voxel_id, relation_type, scope, weight, cross_experiment_ids
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            edge.edge_id, edge.source_voxel_id, edge.target_voxel_id,
            edge.relation_type, edge.scope.name, edge.weight,
            json.dumps(edge.cross_experiment_ids) if edge.cross_experiment_ids else None
        ))
        self.conn.commit()
        self._increment_revision()

    def get_voxel(self, voxel_id: str) -> Optional[HyperVoxel]:
        row = self.conn.execute("SELECT * FROM voxels WHERE voxel_id = ?", (voxel_id,)).fetchone()
        if not row:
            return None
        return self._row_to_voxel(row)
        
    def _row_to_voxel(self, row: sqlite3.Row) -> HyperVoxel:
        auth = AuthoritativeReference(
            store_kind=row["store_kind"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            entity_version=row["entity_version"],
            content_hash=row["content_hash"],
            experiment_id=row["experiment_id"]
        )
        emb_meta = None
        if row["embedding_model_id"]:
            emb_meta = EmbeddingMetadata(
                embedding_model_id=row["embedding_model_id"],
                embedding_dimension=row["embedding_dimension"],
                embedding_version=row["embedding_version"]
            )
            
        sp_meta = None
        if row["layout_algorithm"]:
            sp_meta = SpatialProvenance(
                layout_algorithm=row["layout_algorithm"],
                layout_version=row["layout_version"],
                layout_seed=row["layout_seed"],
                temporal_basis=TemporalBasis[row["temporal_basis"]]
            )
            
        return HyperVoxel(
            voxel_id=row["voxel_id"],
            memory_class=MemoryClass[row["memory_class"]],
            authoritative_ref=auth,
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
            embedding_metadata=emb_meta,
            spatial_coords=tuple(json.loads(row["spatial_coords"])) if row["spatial_coords"] else None,
            temporal_coord=row["temporal_coord"],
            spatial_provenance=sp_meta,
            cognitive_activation=row["cognitive_activation"],
            access_count=row["access_count"],
            last_accessed=row["last_accessed"],
            semantic_label=row["semantic_label"]
        )

    def get_edges_for(self, voxel_id: str) -> List[HyperEdge]:
        rows = self.conn.execute("SELECT * FROM edges WHERE source_voxel_id = ? OR target_voxel_id = ?", (voxel_id, voxel_id)).fetchall()
        return [self._row_to_edge(row) for row in rows]

    def _row_to_edge(self, row: sqlite3.Row) -> HyperEdge:
        return HyperEdge(
            edge_id=row["edge_id"],
            source_voxel_id=row["source_voxel_id"],
            target_voxel_id=row["target_voxel_id"],
            relation_type=row["relation_type"],
            scope=Scope[row["scope"]],
            weight=row["weight"],
            cross_experiment_ids=json.loads(row["cross_experiment_ids"]) if row["cross_experiment_ids"] else None
        )

    def get_all_voxels(self) -> List[HyperVoxel]:
        rows = self.conn.execute("SELECT * FROM voxels").fetchall()
        return [self._row_to_voxel(r) for r in rows]
