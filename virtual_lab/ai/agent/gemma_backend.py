import json
import mlx.core as mx
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw

from virtual_lab.ai.providers.gemma4_unified.loader import Gemma4UnifiedLoader
from virtual_lab.ai.providers.gemma4_unified.processor import Gemma4UnifiedProcessor

@dataclass
class GemmaRuntimeConfig:
    checkpoint_path: str = "/Users/hanna/.lmstudio/models/lmstudio-community/gemma-4-12B-it-MLX-4bit"
    local_only: bool = True
    max_context_budget: int = 8000
    max_decode_tokens: int = 500
    
class GemmaIdentityError(Exception):
    pass

class GemmaBackend:
    def __init__(self, config: Optional[GemmaRuntimeConfig] = None):
        self.config = config or GemmaRuntimeConfig()
        
        if not self.config.local_only:
            raise ValueError("Local Research Mode requires local_only=True")
            
        print(f"Loading local MLX model from {self.config.checkpoint_path}...")
        loader = Gemma4UnifiedLoader(self.config.checkpoint_path)
        
        # Load config to check certificate without full weight loading first if needed
        # We rely on the loader's generate_certificate output
        self.model, self.processor, certificate = loader.load()
        
        if certificate.get("PRODUCTION_STATUS") != "LOCAL • MULTIMODAL MASK VERIFIED":
            raise GemmaIdentityError(f"Checkpoint identity mismatch: {certificate.get('PRODUCTION_STATUS')}")
            
    def render_hview_to_image(self, projection_dict: Dict[str, Any]) -> Image.Image:
        # Create a simple 2D projection using PIL for the multimodal model
        width, height = 512, 512
        img = Image.new("RGB", (width, height), "black")
        draw = ImageDraw.Draw(img)
        
        # Simple orthographic projection mapping
        def map_coords(x, y):
            # assume coords are in [-10, 10]
            cx = int((x + 10) / 20 * width)
            cy = int((y + 10) / 20 * height)
            return cx, cy

        nodes = projection_dict.get("nodes", [])
        edges = projection_dict.get("edges", [])
        
        node_pos = {}
        for n in nodes:
            px, py = map_coords(n["position"]["x"], n["position"]["y"])
            node_pos[n["render_id"]] = (px, py)
            
        for e in edges:
            if e["source"] in node_pos and e["target"] in node_pos:
                sx, sy = node_pos[e["source"]]
                tx, ty = node_pos[e["target"]]
                draw.line((sx, sy, tx, ty), fill=e.get("color", "gray"), width=int(e.get("width", 2)))
                
        for n in nodes:
            px, py = node_pos[n["render_id"]]
            r = n.get("size", 5.0)
            color = n.get("color", "white")
            if n.get("shape") == "circle":
                draw.ellipse((px-r, py-r, px+r, py+r), fill=color)
            else:
                draw.rectangle((px-r, py-r, px+r, py+r), fill=color)
            if n.get("label"):
                draw.text((px+r, py-r), n["label"], fill="white")
                
        return img

    def _parse_output(self, text: str) -> Dict[str, Any]:
        import re
        import json
        
        # Bounded repair: find first json block or anything that looks like { ... }
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
            
        text = text.strip()
        
        # Find the first opening brace just to be safe
        start_idx = text.find('{')
        if start_idx != -1:
            text = text[start_idx:]
            
        try:
            # raw_decode extracts the first valid JSON object and ignores trailing data like extra } or tags
            decoder = json.JSONDecoder(strict=False)
            parsed, _ = decoder.raw_decode(text)
            if "type" not in parsed:
                # Attempt to guess based on structure if missing type
                if "tool_name" in parsed:
                    parsed["type"] = "tool_call"
                elif "response" in parsed or "answer" in parsed:
                    parsed["type"] = "answer"
                    parsed["text"] = str(parsed)
                else:
                    raise ValueError("Missing 'type' in output")
                    
            # Adapt schema to what controller expects if needed
            if parsed["type"] == "final_answer":
                parsed["type"] = "answer"
                parsed["text"] = parsed.get("answer", "")
            if "tool" in parsed and "tool_name" not in parsed:
                parsed["tool_name"] = parsed["tool"]
            if "arguments" in parsed and "args" not in parsed:
                parsed["args"] = parsed["arguments"]
                
            return parsed
        except Exception as e:
            raise ValueError(f"MODEL_OUTPUT_INVALID: {str(e)} - Raw text: {text}")

    def __call__(self, context_data: Dict[str, Any], dag_data: Dict[str, Any], stream_callback=None) -> Dict[str, Any]:
        if hasattr(mx, "reset_peak_memory"):
            mx.reset_peak_memory()
            
        # Assemble Prompt
        prompt = f"System Rules:\n{context_data['system_rules']}\n\n"
        prompt += f"Active Experiment: {context_data['active_experiment_identity']}\n"
        prompt += f"User Request: {context_data['user_request']}\n\n"
        
        prompt += f"Tool Schemas: {json.dumps(context_data['tool_schemas'], indent=2)}\n\n"
        
        prompt += f"Reasoning DAG: {json.dumps(dag_data, indent=2)}\n\n"
        
        hview_image = None
        if context_data.get("hview_symbolic_summary"):
            prompt += "HVIEW Image Representation Provided.\n"
            prompt += "<image>\n"
            prompt += f"Symbolic Sidecar:\n{context_data['hview_symbolic_summary']}\n\n"
            
            # The test runner injects actual projection dict into context_data
            if "hview_projection_dict" in context_data:
                hview_image = self.render_hview_to_image(context_data["hview_projection_dict"])
                
        if context_data.get("authoritative_records"):
            prompt += f"Authoritative Records:\n{json.dumps(context_data['authoritative_records'], indent=2)}\n\n"
            
        if context_data.get("tool_results"):
            prompt += f"Recent Tool Results:\n{json.dumps(context_data['tool_results'], indent=2)}\n\n"
            
        prompt += """EPISTEMIC RESPONSE DISCIPLINE:
When answering, you MUST strictly preserve the epistemic state of your sources:
- If a result is SIMULATED, state that it is a simulation output, not an experimental confirmation.
- If it is INFERRED, state it is a mechanistic interpretation.
- If it is MEASURED, state it is a physical measurement.
- If it is EVIDENCE_BACKED, state it is literature support.
Never claim a SIMULATED result "confirms" a physical outcome.

"""
        prompt += "Respond strictly in JSON: {'type': 'tool_call', 'tool_name': '...', 'args': {...}} OR {'type': 'answer', 'text': '...'}.\n"
        
        # Apply Gemma 4 instruction template
        prompt = f"<|turn>user\n{prompt}<turn|>\n<|turn>model\n"
        
        # Processor handles input IDs and visual token embedding
        inputs = self.processor(text=prompt, images=hview_image)
        input_ids = inputs["input_ids"]
        
        # input_ids already contains the soft image tokens (IMAGE_TOKEN_ID * n_patches)
        text_tokens = input_ids.shape[1]
        
        image_soft_tokens = 0
        if "pixel_values" in inputs:
            image_soft_tokens = inputs["pixel_values"].shape[1]
            
        # text_tokens includes the image placeholders, so that's the true sequence length
        total_sequence_positions = text_tokens
        
        if total_sequence_positions > self.config.max_context_budget:
            raise ValueError(f"context overflow: {total_sequence_positions} exceeds budget {self.config.max_context_budget}")
            
        cache = self.model.language_model.make_cache()
        mx.eval(self.model.parameters())
        
        import time
        t0 = time.perf_counter()
        
        # Prefill
        pixel_values = inputs.get("pixel_values")
        image_position_ids = inputs.get("image_position_ids")
        
        out_prefill = self.model(
            inputs=input_ids, 
            pixel_values=pixel_values, 
            image_position_ids=image_position_ids, 
            cache=cache
        )
        
        mx.eval(out_prefill, [c.keys for c in cache], [c.values for c in cache])
        t1 = time.perf_counter()
        prefill_latency = t1 - t0
        
        # Decode loop
        generated_tokens = []
        next_id = mx.argmax(out_prefill[:, -1, :], axis=-1)[0].item()
        
        t2 = time.perf_counter()
        # Common end tokens for Gemma 4: 1 (<eos>), 106 (<turn|>)
        eos_tokens = {self.processor.tokenizer.eos_token_id, 106}
        
        parser = None
        if stream_callback:
            parser = StreamingEnvelopeParser(stream_callback)
            
        brace_depth = 0
        in_string = False
        escaped = False
        json_started = False
        
        for _ in range(self.config.max_decode_tokens):
            if next_id in eos_tokens:
                break
            generated_tokens.append(next_id)
            
            # JSON streaming completion detection
            char = self.processor.tokenizer.decode([next_id])
            if parser:
                parser.feed(char)
                if parser.is_completed:
                    break
            else:
                for c in char:
                    if escaped:
                        escaped = False
                    elif c == '\\':
                        escaped = True
                    elif c == '"':
                        in_string = not in_string
                    elif not in_string:
                        if c == '{':
                            brace_depth += 1
                            json_started = True
                        elif c == '}':
                            brace_depth -= 1
                if json_started and brace_depth == 0 and not in_string:
                    break
                
            dec_in = mx.array([[next_id]])
            out_dec = self.model(inputs=dec_in, cache=cache)
            logits = out_dec[:, -1, :]
            # Sample with temperature 0.1 (multiply logits by 10) to break deterministic traps
            next_id = mx.random.categorical(logits * 10.0).item()
            mx.eval(out_dec, [c.keys for c in cache], [c.values for c in cache])
            
        t3 = time.perf_counter()
        decode_time = t3 - t2
        tokens_per_sec = len(generated_tokens) / decode_time if decode_time > 0 else 0
        
        output_text = self.processor.tokenizer.decode(generated_tokens)
        
        # Metrics
        peak_mem = mx.get_peak_memory() if hasattr(mx, "get_peak_memory") else 0
        active_mem = mx.get_active_memory() if hasattr(mx, "get_active_memory") else 0
        
        self.last_metrics = {
            "text_tokens": text_tokens,
            "image_soft_tokens": image_soft_tokens,
            "total_sequence_positions": total_sequence_positions,
            "prefill_latency": prefill_latency,
            "decode_tokens_per_sec": tokens_per_sec,
            "peak_memory_bytes": peak_mem,
            "active_memory_bytes": active_mem,
            "generated_tokens": len(generated_tokens),
            "sampler": "categorical",
            "temperature": 0.1,
            "max_tokens": self.config.max_decode_tokens
        }
        
        return self._parse_output(output_text)
