from typing import Dict, Any
from .views import HVIEWArtifact, SymbolicSidecar

class Renderer:
    """
    Translates an immutable HVIEW manifest and SymbolicSidecar into a 
    disposable visual projection (rendered state).
    Strictly forbids mutating any scientific payload or authoritative data.
    """
    def __init__(self):
        pass
        
    def render(self, hview: HVIEWArtifact, sidecar: SymbolicSidecar) -> Dict[str, Any]:
        """
        Creates a dictionary projection mapping render_ids to visual properties.
        """
        projection = {
            "view_id": hview.view_id,
            "scene_hash": hview.view_sha256,
            "nodes": [],
            "edges": []
        }
        
        for sn in sidecar.nodes:
            # Find corresponding spatial/activation data from HVIEW canonical content
            # HVIEW nodes are simple dicts
            hview_node = next((n for n in hview.content.nodes if n["voxel_id"] == sn.voxel_id), None)
            
            if not hview_node:
                continue
                
            x, y, z = hview_node.get("spatial_coords", (0.0, 0.0, 0.0))
            act = sn.activation
            
            # Deterministic translation
            visual_node = {
                "render_id": sn.render_id,
                "position": {"x": x, "y": y, "z": z},
                "size": max(1.0, act * 10.0), # Size denotes salience
                "brightness": min(1.0, 0.5 + (act * 0.5)),
                "shape": "circle" if sn.entity_type == "CONCEPT" else "square",
                "color": "red" if sn.authoritative_resolution != "VALID" else "blue",
                "label": hview_node.get("semantic_label", "")
            }
            projection["nodes"].append(visual_node)
            
        for se in sidecar.edges:
            # Edges use uniform width for this deterministic mocked projection
            visual_edge = {
                "render_id": se.render_id,
                "source": se.source,
                "target": se.target,
                "width": 2.0,
                "color": "gray"
            }
            projection["edges"].append(visual_edge)
            
        return projection
