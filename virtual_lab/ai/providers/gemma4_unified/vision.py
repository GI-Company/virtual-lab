import mlx.core as mx
import mlx.nn as nn
from virtual_lab.ai.providers.gemma4_unified.config import VisionConfig

class Gemma4UnifiedVisionEmbedder(nn.Module):
    def __init__(self, config: VisionConfig):
        super().__init__()
        self.config = config
        
        in_channels = 3 * (config.model_patch_size ** 2)
        
        self.patch_ln1 = nn.LayerNorm(in_channels, eps=config.rms_norm_eps)
        
        # We define patch_dense as a normal Linear layer, it will be quantized when loaded
        self.patch_dense = nn.Linear(in_channels, config.mm_embed_dim)
        
        self.patch_ln2 = nn.LayerNorm(config.mm_embed_dim, eps=config.rms_norm_eps)
        
        self.pos_embedding = mx.zeros((config.mm_posemb_size, 2, config.mm_embed_dim))
        self.pos_norm = nn.LayerNorm(config.mm_embed_dim, eps=config.rms_norm_eps)
        
    def __call__(self, hidden_states, pos_ids):
        # hidden_states: [B, num_patches, in_channels]
        
        hidden_states = self.patch_ln1(hidden_states)
        hidden_states = self.patch_dense(hidden_states)
        hidden_states = self.patch_ln2(hidden_states)
        
        # Factorized 2D Positional Embeddings
        # pos_embedding shape: [mm_posemb_size, 2, mm_embed_dim]
        # pos_ids shape: [B, num_patches, 2]
        
        # To fetch positional embeddings:
        y_pos = self.pos_embedding[pos_ids[..., 0], 0, :]
        x_pos = self.pos_embedding[pos_ids[..., 1], 1, :]
        pos_emb = y_pos + x_pos
        
        hidden_states = hidden_states + pos_emb
        hidden_states = self.pos_norm(hidden_states)
        
        return hidden_states


