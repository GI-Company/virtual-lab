from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class TextConfig:
    vocab_size: int = 262144
    hidden_size: int = 3840
    num_hidden_layers: int = 48
    num_attention_heads: int = 16
    num_key_value_heads: int = 8
    head_dim: int = 256
    global_head_dim: int = 512
    intermediate_size: int = 15360
    rms_norm_eps: float = 1e-6
    rope_parameters: Optional[Dict] = None
    hidden_activation: str = "gelu_pytorch_tanh"
    layer_types: list[str] = field(default_factory=list)
    sliding_window: int = 1024
    tie_word_embeddings: bool = True
    num_kv_shared_layers: int = 0
    hidden_size_per_layer_input: int = 0
    attention_k_eq_v: bool = True
    final_logit_softcapping: float = 30.0
    use_double_wide_mlp: bool = False
    enable_moe_block: bool = False
    num_global_key_value_heads: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict) -> "TextConfig":
        return cls(
            vocab_size=data.get("vocab_size", 262144),
            hidden_size=data.get("hidden_size", 3840),
            num_hidden_layers=data.get("num_hidden_layers", 48),
            num_attention_heads=data.get("num_attention_heads", 16),
            num_key_value_heads=data.get("num_key_value_heads", 8),
            head_dim=data.get("head_dim", 256),
            global_head_dim=data.get("global_head_dim", 512),
            intermediate_size=data.get("intermediate_size", 15360),
            rms_norm_eps=data.get("rms_norm_eps", 1e-6),
            rope_parameters=data.get("rope_parameters", None),
            hidden_activation=data.get("hidden_activation", "gelu_pytorch_tanh"),
            layer_types=data.get("layer_types", []),
            sliding_window=data.get("sliding_window", 1024),
            tie_word_embeddings=data.get("tie_word_embeddings", True),
            num_kv_shared_layers=data.get("num_kv_shared_layers", 0),
            hidden_size_per_layer_input=data.get("hidden_size_per_layer_input", 0),
            attention_k_eq_v=data.get("attention_k_eq_v", True),
            final_logit_softcapping=data.get("final_logit_softcapping", 30.0),
            use_double_wide_mlp=data.get("use_double_wide_mlp", False),
            enable_moe_block=data.get("enable_moe_block", False),
            num_global_key_value_heads=data.get("num_global_key_value_heads", None)
        )

@dataclass
class VisionConfig:
    patch_size: int = 16
    model_patch_size: int = 48
    patch_dim: int = 6912
    mm_embed_dim: int = 3840
    mm_posemb_size: int = 1120
    num_soft_tokens: int = 280
    output_proj_dims: int = 3840
    rms_norm_eps: float = 1e-6

    @classmethod
    def from_dict(cls, data: dict) -> "VisionConfig":
        return cls(
            patch_size=data.get("patch_size", 16),
            model_patch_size=data.get("model_patch_size", 48),
            patch_dim=data.get("patch_dim", 6912),
            mm_embed_dim=data.get("mm_embed_dim", 3840),
            mm_posemb_size=data.get("mm_posemb_size", 1120),
            num_soft_tokens=data.get("num_soft_tokens", 280),
            output_proj_dims=data.get("output_proj_dims", 3840),
            rms_norm_eps=data.get("rms_norm_eps", 1e-6)
        )

@dataclass
class AudioConfig:
    audio_embed_dim: int = 640
    hidden_size: int = 640
    output_proj_dims: int = 640

    @classmethod
    def from_dict(cls, data: dict) -> "AudioConfig":
        return cls(
            audio_embed_dim=data.get("audio_embed_dim", 640),
            hidden_size=data.get("hidden_size", 640),
            output_proj_dims=data.get("output_proj_dims", 640)
        )

@dataclass
class Gemma4UnifiedConfig:
    text_config: TextConfig
    vision_config: VisionConfig
    audio_config: Optional[AudioConfig] = None
    model_type: str = "gemma4_unified"
    image_token_id: int = 258880
    audio_token_id: int = 258881
    boi_token_id: int = 255999
    eoi_token_id: int = 258882

    @classmethod
    def from_dict(cls, data: dict) -> "Gemma4UnifiedConfig":
        return cls(
            text_config=TextConfig.from_dict(data.get("text_config", {})),
            vision_config=VisionConfig.from_dict(data.get("vision_config", {})),
            audio_config=AudioConfig.from_dict(data["audio_config"]) if "audio_config" in data else None,
            model_type=data.get("model_type", "gemma4_unified"),
            image_token_id=data.get("image_token_id", 258880),
            audio_token_id=data.get("audio_token_id", 258881),
            boi_token_id=data.get("boi_token_id", 255999),
            eoi_token_id=data.get("eoi_token_id", 258882)
        )
