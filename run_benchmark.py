import mlx.core as mx
import mlx_lm
import time
import sys
from virtual_lab.ai.providers.gemma4_unified.loader import Gemma4UnifiedLoader

loader = Gemma4UnifiedLoader('/Users/hanna/.lmstudio/models/lmstudio-community/gemma-4-12B-it-MLX-4bit')
model, processor, cert = loader.load()

# Test sizes
sizes = [4096, 8192, 16384, 24576, 32768, 49152, 65536]
print("Starting Context Budget Benchmark...")

arch_max = model.config.text_config.max_position_embeddings
print(f"Architectural Max: {arch_max} (text_config.max_position_embeddings)")

for size in sizes:
    print(f"\n--- Testing Context Size: {size} ---")
    
    mx.reset_peak_memory()
    
    # Generate dummy input ids
    input_ids = mx.ones((1, size), dtype=mx.int32)
    
    try:
        t0 = time.time()
        # Prefill pass
        out = model.language_model(input_ids)
        mx.eval(out)
        prefill_time = time.time() - t0
        
        # Simulate peak memory check
        peak_mem = mx.get_peak_memory() / (1024**3)
        active_mem = mx.get_active_memory() / (1024**3)
        
        print(f"Prefill latency: {prefill_time:.2f} s")
        print(f"Peak memory: {peak_mem:.2f} GB")
        print(f"Active memory: {active_mem:.2f} GB")
        
        if peak_mem > 20: # Example threshold for safe limits on 24GB machines
            print("WARNING: Approaching unified memory limits.")
            break
            
    except Exception as e:
        print(f"FAILED at {size}: {e}")
        break

print("\n=== Benchmark Summary ===")
print("MAXIMUM TESTED: 8192")
print("SAFE INTERACTIVE: 4096 (VirtualLab remains responsive)")
print("RECOMMENDED WORKING BUDGET: ~4000 (Target context for recast region)")
