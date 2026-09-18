from dataclasses import dataclass

@dataclass(frozen=True)
class ActivationBreakdown:
    weight_set_id: str
    task_relevance: float
    semantic_relevance: float
    graph_relevance: float
    recency_factor: float
    episodic_relevance: float
    raw_score: float
    normalized_score: float

class CognitiveStateUpdater:
    """
    Dedicated boundary for mutating cognitive state.
    Strictly forbids mutating scientific payloads.
    """
    @staticmethod
    def update_cognitive_state(
        voxel,
        activation_breakdown: ActivationBreakdown,
        access_count_increment: int = 1,
        last_accessed_timestamp: float = 0.0
    ):
        voxel.cognitive_activation = activation_breakdown.normalized_score
        voxel.access_count += access_count_increment
        if last_accessed_timestamp > voxel.last_accessed:
            voxel.last_accessed = last_accessed_timestamp
