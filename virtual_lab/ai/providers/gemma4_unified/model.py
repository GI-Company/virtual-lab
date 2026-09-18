import mlx.core as mx
import mlx.nn as nn
from virtual_lab.ai.providers.gemma4_unified.config import Gemma4UnifiedConfig
from virtual_lab.ai.providers.gemma4_unified.vision import Gemma4UnifiedVisionEmbedder
from mlx_lm.models.gemma4_text import Model as Gemma4TextModel, ModelArgs as Gemma4TextModelArgs

class Gemma4UnifiedModel(nn.Module):
    def __init__(self, config: Gemma4UnifiedConfig):
        super().__init__()
        self.config = config
        
        # Instantiate language model
        import inspect
        valid_keys = inspect.signature(Gemma4TextModelArgs).parameters.keys()
        text_kwargs = {k: v for k, v in config.text_config.__dict__.items() if k in valid_keys}
        text_args = Gemma4TextModelArgs(**text_kwargs)
        self.language_model = Gemma4TextModel(text_args)
        
        # Instantiate vision components
        self.vision_embedder = Gemma4UnifiedVisionEmbedder(config.vision_config)
        self.embed_vision = nn.Module()
        self.embed_vision.embedding_projection = nn.Linear(
            config.vision_config.output_proj_dims, 
            config.text_config.hidden_size
        )
        
        # Optional audio components could be stubbed here
        if config.audio_config:
            self.embed_audio = nn.Module()
            self.embed_audio.embedding_projection = nn.Linear(
                config.audio_config.output_proj_dims,
                config.text_config.hidden_size
            )
            
    def __call__(self, inputs=None, input_ids=None, pixel_values=None, image_position_ids=None, cache=None, **kwargs):
        # Support dict inputs from processor
        if isinstance(inputs, dict):
            input_ids = inputs.get("input_ids", input_ids)
            pixel_values = inputs.get("pixel_values", pixel_values)
            image_position_ids = inputs.get("image_position_ids", image_position_ids)
        elif inputs is not None and input_ids is None:
            input_ids = inputs
            
        IMAGE_TOKEN_ID = 258880
        
        # 1. Forward through vision_embedder if pixel_values are present
        input_embeddings = self.language_model.model.embed_tokens(input_ids)
        
        if pixel_values is not None:
            vision_embeds = self.vision_embedder(pixel_values, image_position_ids)
            vision_embeds = self.embed_vision.embedding_projection(vision_embeds)
            
            # Find image tokens
            image_mask = input_ids == IMAGE_TOKEN_ID
            
            # Assuming 1 image per batch for simplicity in this replacement logic,
            # or flattened masking. MLX allows boolean indexing:
            # input_embeddings[image_mask] = vision_embeds.reshape(-1, vision_embeds.shape[-1])
            # BUT mlx arrays are immutable in python syntax unless using mx.where or scatter
            
            B, L, D = input_embeddings.shape
            
            # Use mx.where to conditionally replace embeddings
            # We need to broadcast vision_embeds to the right positions.
            # A simple way when there is exactly one continuous block of <image> tokens:
            # But the mask might have multiple images.
            # MLX scatter:
            # We can flatten everything
            flat_embeddings = mx.reshape(input_embeddings, (-1, D))
            flat_mask = mx.reshape(image_mask, (-1,))
            
            # Extract indices where mask is True
            # In MLX, we can do:
            # We need to generate the indices. MLX has mx.nonzero
            # Let's use it:
            # This is robust for multiple images and arbitrary positions
            # Actually, mlx_lm model expects just input_embeddings.
            # Let's use boolean indexing if supported by MLX update
            
            indices = mx.arange(flat_mask.size)
            # Use a mask to get the indices to update
            # MLX scatter: mx.scatter(operand, indices, updates, axis=0)
            # Wait, MLX doesn't have advanced boolean array assignment in python perfectly yet.
            # Let's do it safely:
            # If flat_mask sum == vision_embeds total patches
            vision_flat = mx.reshape(vision_embeds, (-1, D))
            
            # We can use mx.where if we can pad vision_flat to same size as flat_embeddings
            # Or we can just build the new embeddings by looping over batch if needed,
            # but MLX compiles this so we should use array ops.
            # A common way: 
            # We can't easily scatter without knowing indices.
            # Actually, MLX array assignment `a[mask] = b` is supported!
            
            flat_embeddings[flat_mask] = vision_flat
            input_embeddings = mx.reshape(flat_embeddings, (B, L, D))
        
        # 2. Extract configuration
        num_hidden_layers = self.config.text_config.num_hidden_layers
        
        # 3. Handle MultimodalSequenceState tracking
        # If cache is provided and has a custom state attached, we retrieve it.
        # Otherwise, we create a new one.
        from virtual_lab.ai.providers.gemma4_unified.masks import (
            MultimodalSequenceState, build_multimodal_topology, build_attention_mask, classify_multimodal_tokens
        )
        
        if cache is not None and hasattr(cache[0], "mm_state") and cache[0].mm_state is not None:
            # Decoding step
            mm_state = cache[0].mm_state
            # Determine absolute offset from current sequence length
            offset = mm_state.sequence_length
            
            # Identify current tokens
            token_types = classify_multimodal_tokens(input_ids, self.config)
            
            # For decoding single token, block ID is usually 0 unless it's inside an image block, 
            # but standard autoregressive generation produces text. If it produced an image, we'd need to link it.
            # We assume generation is TEXT or we can continue block ID.
            # For simplicity, if we are generating, block_id is 0.
            block_ids = mx.zeros_like(token_types)
            
            # Update state
            mm_state.append(token_types, block_ids)
            
            # Topology for current query
            topology = build_multimodal_topology(input_ids, self.config, offset=offset)
        else:
            # Prefill step
            offset = 0
            topology = build_multimodal_topology(input_ids, self.config, offset=offset)
            mm_state = MultimodalSequenceState(
                token_types=topology.token_types,
                block_ids=topology.block_ids,
                sequence_length=input_ids.shape[-1]
            )
            # If cache exists, attach the state
            if cache is not None and len(cache) > 0:
                cache[0].mm_state = mm_state
        
        # 4. Forward through language_model using custom loop
        lm = self.language_model.model
        
        h = input_embeddings * lm.embed_scale
        
        # per_layer_inputs handling (for 2B/4B models)
        if lm.hidden_size_per_layer_input:
            per_layer_inputs = lm._get_per_layer_inputs(input_ids, input_embeddings)
            per_layer_inputs = lm._project_per_layer_inputs(h, per_layer_inputs)
            per_layer_inputs = [per_layer_inputs[:, :, i, :] for i in range(len(lm.layers))]
        else:
            per_layer_inputs = [None] * len(lm.layers)
            
        if cache is None:
            cache = [None] * len(lm.layers)
        else:
            cache = cache + [None] * (len(lm.layers) - len(cache))
            
        # Instead of lm._make_masks(h, cache), we build our architecture-owned masks!
        masks = []
        # Cache identical masks to avoid recomputation
        mask_cache = {}
        
        for l in lm.layers:
            layer_type = l.layer_type
            if layer_type not in mask_cache:
                window_size = lm.window_size if layer_type == "sliding_attention" else None
                m = build_attention_mask(
                    topology=topology,
                    attention_type=layer_type,
                    cache_state=mm_state,
                    window_size=window_size
                )
                if m is not None:
                    m = m.astype(h.dtype)
                mask_cache[layer_type] = m
            masks.append(mask_cache[layer_type])
            
        intermediates = [(None, None)] * len(lm.layers)
        for idx, (layer, c, mask_proto, prev_idx, per_layer_input) in enumerate(
            zip(lm.layers, cache, masks, lm.previous_kvs, per_layer_inputs)
        ):
            kvs, k_offset = intermediates[prev_idx]
            
            # Adjust mask length for RotatingKVCache
            mask = mask_proto
            if c is not None and hasattr(c, "max_size"):
                step = h.shape[1]
                if step == 1:
                    expected_k_len = min(c.offset + step, c.max_size)
                    if mask is not None and mask.shape[-1] > expected_k_len:
                        mask = mask[..., -expected_k_len:]
                    
            h, kvs, k_offset = layer(
                h, mask, c, per_layer_input=per_layer_input, shared_kv=kvs, offset=k_offset
            )
            intermediates[idx] = (kvs, k_offset)
            
        out = lm.norm(h)
        
        # Logit projection handling
        if self.language_model.tie_word_embeddings:
            out = self.language_model.model.embed_tokens.as_linear(out)
        else:
            out = self.language_model.lm_head(out)
            
        if self.language_model.final_logit_softcapping is not None:
            from mlx_lm.models.gemma4_text import logit_softcap
            out = logit_softcap(self.language_model.final_logit_softcapping, out)
            
        return out
            
    def sanitize(self, weights):
        # We don't sanitize anything here, we load weights faithfully as provided.
        # But mlx_lm's loader might expect sanitize on the model.
        # Let's map any top-level language_model.x -> language_model.x 
        # Actually, the weights dict from safetensors already has language_model.*, vision_embedder.*
        return weights
