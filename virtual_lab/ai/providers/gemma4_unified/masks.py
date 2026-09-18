from enum import IntEnum
from dataclasses import dataclass
import mlx.core as mx
from .config import Gemma4UnifiedConfig

class MMTokenType(IntEnum):
    TEXT = 0
    IMAGE_START = 1
    IMAGE = 2
    IMAGE_END = 3
    PADDING = 4

@dataclass(frozen=True)
class MultimodalTopology:
    token_types: mx.array
    block_ids: mx.array
    absolute_positions: mx.array

@dataclass
class MultimodalSequenceState:
    token_types: mx.array
    block_ids: mx.array
    sequence_length: int
    
    def append(self, token_types: mx.array, block_ids: mx.array):
        self.token_types = mx.concatenate([self.token_types, token_types], axis=-1)
        self.block_ids = mx.concatenate([self.block_ids, block_ids], axis=-1)
        self.sequence_length = self.token_types.shape[-1]

def classify_multimodal_tokens(input_ids: mx.array, config: Gemma4UnifiedConfig) -> mx.array:
    """
    Classifies token IDs into MMTokenType integers.
    Shape: (..., seq_len)
    """
    token_types = mx.zeros_like(input_ids)
    
    # By default, everything is TEXT (0)
    token_types = mx.where(input_ids == config.boi_token_id, MMTokenType.IMAGE_START, token_types)
    token_types = mx.where(input_ids == config.image_token_id, MMTokenType.IMAGE, token_types)
    token_types = mx.where(input_ids == config.eoi_token_id, MMTokenType.IMAGE_END, token_types)
    # config.pad_token_id usually 0 for Gemma, assuming TEXT is default. Let's explicitly check padding if needed.
    # We will assume pad_token_id = 0, but MLX LM Gemma config says pad_token_id: int = 0.
    # To be safe, if input_ids == 0, maybe it's PADDING? But 0 is `<pad>` or `<unk>`. We'll leave as TEXT if padding isn't strictly masked yet.
    # Wait, the user specifically mentioned PADDING.
    # The reference gemma config has pad_token_id=0.
    if hasattr(config.text_config, "pad_token_id"):
        token_types = mx.where(input_ids == config.text_config.pad_token_id, MMTokenType.PADDING, token_types)
        
    return token_types

def build_multimodal_topology(input_ids: mx.array, config: Gemma4UnifiedConfig, offset: int = 0) -> MultimodalTopology:
    """
    Constructs the sequence topology including token types and block IDs.
    """
    token_types = classify_multimodal_tokens(input_ids, config)
    
    # Build block IDs.
    # We can do this efficiently:
    # A block starts when we see an IMAGE token and the previous wasn't IMAGE, 
    # but more simply, since we want every contiguous sequence of IMAGE tokens to have a unique ID:
    # In MLX, we can compute diffs to find boundaries, or just cumulative sums of IMAGE_START.
    is_start = token_types == MMTokenType.IMAGE_START
    block_ids = mx.cumsum(is_start, axis=-1)
    
    # We only care about block_ids for IMAGE tokens. For others, set to 0.
    block_ids = mx.where(token_types == MMTokenType.IMAGE, block_ids, 0)
    
    seq_len = input_ids.shape[-1]
    absolute_positions = mx.arange(offset, offset + seq_len)
    
    return MultimodalTopology(
        token_types=token_types,
        block_ids=block_ids,
        absolute_positions=absolute_positions
    )

def build_attention_mask(
    topology: MultimodalTopology,
    attention_type: str,
    cache_state: MultimodalSequenceState = None,
    window_size: int = None
) -> mx.array:
    """
    Builds the boolean attention mask (1 = blocked, 0 = allowed, or vice versa depending on scaled_dot_product_attention).
    Actually, mlx_lm expects standard causal mask: 
    Typically, mlx_lm `create_attention_mask` returns additive masks (-inf for blocked, 0 for allowed).
    Let's return a boolean mask (True for ALLOWED, False for BLOCKED) and then convert if needed.
    Actually, mlx's scaled_dot_product_attention expects additive mask if it's float, or boolean mask (True=mask out).
    Let's check mlx_lm.models.base.create_attention_mask. It returns an additive mask with -inf.
    We will return additive mask directly.
    """
    
    query_types = topology.token_types
    query_blocks = topology.block_ids
    query_pos = topology.absolute_positions
    
    if cache_state is not None:
        key_types = cache_state.token_types
        key_blocks = cache_state.block_ids
        # KV cache includes the current tokens we are adding!
        # Because we update the sequence state BEFORE generating the mask for the current forward pass.
        # Wait, if we are doing prefill, query_pos is 0..L, and key_pos is 0..L.
        key_pos = mx.arange(0, cache_state.sequence_length)
    else:
        key_types = query_types
        key_blocks = query_blocks
        key_pos = query_pos

    # Broadcast shapes for pairwise comparison
    # query: (..., L_q, 1)
    # key: (..., 1, L_k)
    Q_len = query_types.shape[-1]
    K_len = key_types.shape[-1]
    
    # Reshape for broadcasting
    q_pos = mx.expand_dims(query_pos, -1)  # (L_q, 1)
    k_pos = mx.expand_dims(key_pos, 0)     # (1, L_k)
    
    q_type = mx.expand_dims(query_types, -1)
    k_type = mx.expand_dims(key_types, -2) # if batch is present, shape is (B, 1, L_k)
    
    q_block = mx.expand_dims(query_blocks, -1)
    k_block = mx.expand_dims(key_blocks, -2)
    
    # 1. Base Causal allowed: key_pos <= query_pos
    is_causal = k_pos <= q_pos
    
    # 2. Vision Bidirectional allowed: 
    # Same vision block, meaning both are IMAGE tokens and have the same non-zero block_id
    is_vision_q = q_type == MMTokenType.IMAGE
    is_vision_k = k_type == MMTokenType.IMAGE
    same_block = (q_block == k_block) & (q_block > 0)
    
    is_bidirectional_vision = is_vision_q & is_vision_k & same_block
    
    # Combine allowed conditions
    allowed = is_causal | is_bidirectional_vision
    
    # 3. Apply Padding block (disallow attending to padding)
    is_padding_k = k_type == MMTokenType.PADDING
    allowed = allowed & (~is_padding_k)
    
    # 4. Apply Sliding Window policy if needed
    if attention_type == "sliding_attention" and window_size is not None:
        # sliding window means you can only attend to keys within `window_size` distance
        # Wait, does sliding window apply to vision blocks? 
        # The user says: "A visual block must retain the required visual relationship semantics while respecting whichever global/sliding behavior the architecture requires."
        # If the window is 512, and the vision block is 1000 tokens long, does sliding window truncate the vision block?
        # Typically, yes, causal distance <= window_size.
        # Wait, if vision is bidirectional, it means distance |q_pos - k_pos| <= window_size, or just causal sliding + vision sliding?
        # "respecting whichever global/sliding behavior".
        # Let's enforce distance constraint:
        # For sliding, allowed if (q_pos - k_pos) < window_size
        # But for bidirectional vision, what is the distance? 
        # If j > i (future), k_pos - q_pos < window_size.
        # So we can just enforce |q_pos - k_pos| < window_size for everyone.
        # Actually, standard sliding window: q_pos - k_pos < window_size.
        # If bidirectional, we also need k_pos - q_pos < window_size. 
        # So absolute distance < window_size.
        within_window = mx.abs(q_pos - k_pos) < window_size
        allowed = allowed & within_window

    # Create additive mask
    # mlx_lm expects mask shaped (1, 1, L_q, L_k) or (B, 1, L_q, L_k)
    # The additive mask has 0 for allowed, -inf for disallowed
    
    mask = mx.where(allowed, mx.zeros_like(allowed, dtype=mx.float32), mx.full(allowed.shape, -float('inf'), dtype=mx.float32))
    
    # Ensure shape is (B, 1, L_q, L_k) if batch is present
    if mask.ndim == 2:
        mask = mask[None, None, :, :]
    elif mask.ndim == 3:
        mask = mask[:, None, :, :]
        
    return mask

