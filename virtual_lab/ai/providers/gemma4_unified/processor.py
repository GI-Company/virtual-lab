import mlx.core as mx
from mlx_lm.tokenizer_utils import TokenizerWrapper
from virtual_lab.ai.providers.gemma4_unified.config import Gemma4UnifiedConfig

class Gemma4UnifiedProcessor:
    def __init__(self, tokenizer: TokenizerWrapper, config: Gemma4UnifiedConfig):
        self.tokenizer = tokenizer
        self.config = config
        
    def __call__(self, text=None, images=None, **kwargs):
        """
        Process text and images into inputs suitable for Gemma4UnifiedModel.
        """
        result = {}
        
        IMAGE_TOKEN_ID = 256000
        
        # Calculate patches first if images are present
        if images is not None:
            # Handle single image or list
            if not isinstance(images, list):
                images = [images]
            
            all_pixel_values = []
            all_pos_ids = []
            all_num_patches = []
            
            # Constants
            P = self.config.vision_config.patch_size # 16
            M = self.config.vision_config.model_patch_size // P # 48 // 16 = 3
            patch_dim = P * M # 48
            
            for img in images:
                width, height = img.size
                
                # Simple resize to fit a multiple of patch_dim
                new_w = max(patch_dim, (width // patch_dim) * patch_dim)
                new_h = max(patch_dim, (height // patch_dim) * patch_dim)
                
                img = img.resize((new_w, new_h))
                
                import numpy as np
                img_array = mx.array(np.array(img)) / 255.0
                img_array = mx.transpose(img_array, (2, 0, 1))
                
                C, H, W = img_array.shape
                H_P = H // patch_dim
                W_P = W // patch_dim
                
                reshaped = mx.reshape(img_array, (C, H_P, M, P, W_P, M, P))
                patches = mx.transpose(reshaped, (1, 4, 2, 5, 0, 3, 6))
                flat_patches = mx.reshape(patches, (H_P * W_P, M * M * C * P * P))
                all_pixel_values.append(flat_patches)
                
                y_coords = mx.arange(H_P)[:, None]
                x_coords = mx.arange(W_P)[None, :]
                
                y_grid = mx.broadcast_to(y_coords, (H_P, W_P))
                x_grid = mx.broadcast_to(x_coords, (H_P, W_P))
                
                pos_ids = mx.stack([y_grid, x_grid], axis=-1)
                pos_ids = mx.reshape(pos_ids, (H_P * W_P, 2))
                all_pos_ids.append(pos_ids)
                
                all_num_patches.append(H_P * W_P)
            
            result["pixel_values"] = mx.stack(all_pixel_values, axis=0)
            result["image_position_ids"] = mx.stack(all_pos_ids, axis=0)
        
        if text is not None:
            if isinstance(text, str):
                if images is not None and "<image>" in text:
                    # Basic multi-image support: replace <image> with correct number of placeholders
                    parts = text.split("<image>")
                    input_ids = []
                    img_idx = 0
                    
                    BOI_TOKEN_ID = 255999
                    IMAGE_TOKEN_ID = 258880
                    EOI_TOKEN_ID = 258882
                    
                    for i, part in enumerate(parts):
                        if part:
                            input_ids.extend(self.tokenizer.encode(part))
                        if i < len(parts) - 1:
                            if img_idx < len(all_num_patches):
                                n_patches = all_num_patches[img_idx]
                                input_ids.append(BOI_TOKEN_ID)
                                input_ids.extend([IMAGE_TOKEN_ID] * n_patches)
                                input_ids.append(EOI_TOKEN_ID)
                                img_idx += 1
                    result["input_ids"] = mx.array([input_ids])
                else:
                    tokens = self.tokenizer.encode(text)
                    result["input_ids"] = mx.array([tokens])
            elif isinstance(text, list):
                result["input_ids"] = mx.array(text)
            
        return result
