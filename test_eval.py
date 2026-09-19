import os
import mlx.core as mx
os.environ['VIRTUALLAB_LOCAL_MODEL'] = '/Users/hanna/.lmstudio/models/lmstudio-community/gemma-4-E2B-it-MLX-4bit'
from virtual_lab.ai.agent.gemma_backend import GemmaBackend
b = GemmaBackend()
out = b({"system_rules": "", "active_experiment_identity": "E-001", "user_request": "hello", "tool_schemas": {}}, {})
print("Generation:", out)
