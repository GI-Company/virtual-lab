import mlx.core as mx
from virtual_lab.ai.providers.gemma4_unified.loader import Gemma4UnifiedLoader
from PIL import Image
import numpy as np

# Create a dummy image
img = Image.fromarray(np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8))

loader = Gemma4UnifiedLoader('/Users/hanna/.lmstudio/models/lmstudio-community/gemma-4-12B-it-MLX-4bit')
model, processor, cert = loader.load()

# Test processor
text = "Look at this image: <image>. What do you see?"
inputs = processor(text=text, images=img)
print("Input IDs shape:", inputs["input_ids"].shape)
print("Pixel values shape:", inputs["pixel_values"].shape)
print("Pos IDs shape:", inputs["image_position_ids"].shape)

# Test model
out = model(inputs)
print("Model output shape:", out.shape)
