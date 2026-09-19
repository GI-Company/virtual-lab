import mlx.core as mx
from mlx_lm.models.gemma4_text import ModelArgs, Model
args = ModelArgs(hidden_size=2048, num_hidden_layers=2, num_attention_heads=8, num_key_value_heads=1, intermediate_size=8192, vocab_size=256000)
m = Model(args)
cache = m.make_cache()
print([(type(c).__name__, hasattr(c, 'max_size'), getattr(c, 'max_size', None)) for c in cache])
