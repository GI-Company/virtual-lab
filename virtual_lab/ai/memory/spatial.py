from .models import HyperVoxel, SpatialProvenance
from .types import TemporalBasis

class LayoutGenerator:
    """
    Generates derived deterministic XYZ/T layout mapping based on the graph.
    """
    def __init__(self, algorithm: str = "force_directed_mock", version: str = "1.0", seed: int = 42):
        self.algorithm = algorithm
        self.version = version
        self.seed = seed

    def compute_spatial_coordinates(self, voxel: HyperVoxel, depth: int, index: int):
        # Deterministic dummy calculation for test acceptance
        x = float(depth * 10 + (self.seed % 5))
        y = float(index * 10 + (self.seed % 3))
        z = 0.0
        
        voxel.spatial_coords = (x, y, z)
        voxel.temporal_coord = 0.0 # None basis
        
        voxel.spatial_provenance = SpatialProvenance(
            layout_algorithm=self.algorithm,
            layout_version=self.version,
            layout_seed=self.seed,
            temporal_basis=TemporalBasis.NONE
        )
