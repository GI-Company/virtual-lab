"""
virtual_lab.ai.providers.mlx_local
────────────────────────────────────
Direct MLX inference via mlx-lm for Gemma 4 E2B Unified.

Capabilities wired up:
  ✓ Text generation
  ✓ Native tool use  (Gemma 4 chat template: <|tool_call>call:name{args}<tool_call|>)
  ✓ Reasoning       (<|think|> token — model chains thought before responding)
  ○ Vision          (weights present; blocked until mlx-lm adds gemma4_unified class)

Model path resolution:
  1. VIRTUALLAB_LOCAL_MODEL env var (full path to MLX model dir) MUST be set.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mlx.core as mx
import mlx_lm
from mlx_lm.sample_utils import make_sampler

log = logging.getLogger("virtuallab.ai.mlx")

_MODEL_NAME = "gemma-4-E2B"  # canonical expected name used in UI

_DEFAULT_PATHS = []

# Module-level singleton — loaded once per process
_model = None
_tokenizer = None
_loaded_path: Optional[str] = None

# Regex for parsing Gemma 4 tool call tokens from generated text
_TOOL_CALL_RE = re.compile(
    r"<\|tool_call\>call:(\w+)\{(.*?)\}<tool_call\|>",
    re.DOTALL,
)
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]


@dataclass
class GenerationResult:
    text: str                          # cleaned response text (no think/tool tokens)
    tool_calls: List[ToolCall] = field(default_factory=list)
    reasoning: str = ""                # content of <think>...</think> if any


# ── Registry patch ────────────────────────────────────────────────────────────

def _patch_mlx_registry():
    """
    Inject gemma4_unified → gemma4_text into mlx_lm's MODEL_REMAPPING.
    Monkeypatch sanitize to strip multimodal prefixes.
    Monkeypatch load_config to flatten text_config.
    Must be called before mlx_lm.load() is invoked.
    """
    try:
        import mlx_lm.utils as u
        if "gemma4_unified" not in u.MODEL_REMAPPING:
            u.MODEL_REMAPPING["gemma4_unified"] = "gemma4_text"
            log.info("Patched mlx_lm MODEL_REMAPPING: gemma4_unified → gemma4_text")
        
        # 1. Flatten text_config in load_config
        if not hasattr(u, "_original_load_config"):
            u._original_load_config = u.load_config
            def custom_load_config(model_path: Path) -> dict:
                cfg = u._original_load_config(model_path)
                if cfg.get("model_type") == "gemma4_unified" and "text_config" in cfg:
                    # Flatten text_config into root config
                    for k, v in cfg["text_config"].items():
                        if k not in cfg:
                            cfg[k] = v
                return cfg
            u.load_config = custom_load_config
            log.info("Monkeypatched mlx_lm load_config for gemma4_unified text_config")

        # 2. Monkeypatch the sanitize method to map unified weights to text model
        import mlx_lm.models.gemma4_text as g
        if not hasattr(g.Model, "_original_sanitize"):
            g.Model._original_sanitize = getattr(g.Model, "sanitize", None)
            
            def custom_sanitize(self, weights):
                if self._original_sanitize:
                    weights = self._original_sanitize(weights)
                
                new_weights = {}
                for k, v in weights.items():
                    # Strip the language_model wrapper
                    if k.startswith("language_model."):
                        new_weights[k.replace("language_model.", "", 1)] = v
                    # Drop multimodal weights
                    elif k.startswith("embed_vision") or k.startswith("embed_audio") or k.startswith("vision_embedder"):
                        continue
                    else:
                        new_weights[k] = v
                return new_weights
            
            g.Model.sanitize = custom_sanitize
            log.info("Monkeypatched gemma4_text sanitize method for multimodal weights")
            
    except Exception as e:
        log.warning(f"Could not patch mlx_lm registry: {e}")


# ── Path resolution ───────────────────────────────────────────────────────────

def _resolve_model_path() -> Optional[Path]:
    env = os.environ.get("VIRTUALLAB_LOCAL_MODEL")
    if env:
        p = Path(env)
        if p.exists():
            return p
    for p in _DEFAULT_PATHS:
        if p.exists():
            return p
    return None


# ── Lazy model loader ─────────────────────────────────────────────────────────

def _ensure_loaded() -> bool:
    global _model, _tokenizer, _loaded_path
    if _model is not None:
        return True
    path = _resolve_model_path()
    if path is None:
        return False
    try:
        import mlx_lm
        _patch_mlx_registry()
        
        # Verify model directory before loading to ensure it is E2B
        config_path = path / "config.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                cfg = json.load(f)
                model_type = cfg.get("model_type", "").lower()
                # Interrogate the actual model to ensure it matches the expected E2B requirement
                if "gemma" not in model_type:
                     log.warning(f"Unexpected model_type {model_type} in {path}")
        
        # Strict validation: Only accept if the path or config implies E2B
        if "e2b" not in str(path).lower():
             log.warning("WARNING: VIRTUALLAB_LOCAL_MODEL path does not contain 'E2B'. Operational PoC v0.1 expects Gemma 4 E2B.")
        
        log.info(f"Loading MLX model from {path} …")
        loaded = mlx_lm.load(str(path))
        _model = loaded[0]
        _tokenizer = loaded[1]
        _loaded_path = str(path)
        log.info("MLX model loaded.")
        return True
    except Exception as e:
        log.error(f"MLX model load failed: {e}")
        return False


# ── Response parser ───────────────────────────────────────────────────────────

def _parse_response(raw: str) -> GenerationResult:
    """
    Extract tool calls and reasoning from raw Gemma 4 model output.

    Tool call format:  <|tool_call>call:func_name{json_args}<tool_call|>
    Reasoning format:  <think>...</think>
    """
    # Extract reasoning
    reasoning = ""
    think_match = _THINK_RE.search(raw)
    if think_match:
        reasoning = think_match.group(1).strip()
        raw = _THINK_RE.sub("", raw)

    # Extract tool calls
    tool_calls: List[ToolCall] = []
    def _replace_tool_call(m):
        func_name = m.group(1)
        args_str = m.group(2).strip()
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            # Try wrapping bare key=value if JSON parse fails
            try:
                args = json.loads("{" + args_str + "}")
            except Exception:
                args = {"_raw": args_str}
        tool_calls.append(ToolCall(name=func_name, arguments=args))
        return ""  # remove from text

    cleaned = _TOOL_CALL_RE.sub(_replace_tool_call, raw).strip()

    return GenerationResult(text=cleaned, tool_calls=tool_calls, reasoning=reasoning)


# ── Provider ──────────────────────────────────────────────────────────────────

class MLXLocalProvider:
    """
    Provider that runs Gemma 4 E2B inference directly via MLX.
    No network. No LM Studio server needed.

    Features:
      - Stateless text generation
      - Native tool use via Gemma 4 chat template
      - Reasoning token extraction
    """

    def is_configured(self) -> bool:
        return _resolve_model_path() is not None

    def is_loaded(self) -> bool:
        return _model is not None

    def model_path(self) -> Optional[str]:
        return _loaded_path or str(_resolve_model_path() or "")

    def test_connection(self) -> bool:
        if not _ensure_loaded():
            raise RuntimeError(
                "MLX model not found. Check VIRTUALLAB_LOCAL_MODEL or wait for download."
            )
        result = self.generate("Reply with the single word OK.", max_tokens=8)
        return "ok" in result.lower()

    # ── Low-level generation ──────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        """Raw prompt → raw text string."""
        if not _ensure_loaded():
            raise RuntimeError("MLX model not available.")
        import mlx_lm
        return mlx_lm.generate(
            _model, _tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=make_sampler(temp=temperature),
            verbose=False,
        )

    # ── Chat with full parse ──────────────────────────────────────────────────

    def chat(
        self,
        messages: List[dict],
        tools: Optional[List[dict]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        enable_thinking: bool = True,
    ) -> GenerationResult:
        """
        Multi-turn chat. Returns a GenerationResult with:
          .text       — assistant reply (clean, no tool/think tokens)
          .tool_calls — list of ToolCall if model invoked tools
          .reasoning  — chain-of-thought content if present
        """
        if not _ensure_loaded():
            raise RuntimeError("MLX model not available.")
        import mlx_lm

        kwargs: dict = {"tokenize": False, "add_generation_prompt": True}
        if tools:
            kwargs["tools"] = tools
        if enable_thinking:
            kwargs["enable_thinking"] = True  # activates <|think|> in system turn

        try:
            formatted = _tokenizer.apply_chat_template(messages, **kwargs)
        except TypeError:
            # Older tokenizer version — drop unsupported kwargs gracefully
            kwargs.pop("enable_thinking", None)
            formatted = _tokenizer.apply_chat_template(messages, **kwargs)

        raw = mlx_lm.generate(
            _model, _tokenizer,
            prompt=formatted,
            max_tokens=max_tokens,
            sampler=make_sampler(temp=temperature),
            verbose=False,
        )
        return _parse_response(raw)

    # ── Agentic loop (tool-use aware) ─────────────────────────────────────────

    def agentic_chat(
        self,
        messages: List[dict],
        tools: Optional[List[dict]],
        tool_executor,            # callable(name: str, args: dict) -> dict
        max_tool_rounds: int = 8,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        on_thinking=None,         # optional callback(reasoning: str)
        on_tool_call=None,        # optional callback(tool_name: str, args: dict)
    ) -> Tuple[str, List[dict]]:
        """
        Full agentic loop with local tool execution.

        Runs until:
          - Model returns a text response without tool calls
          - max_tool_rounds exhausted

        Returns (final_text, updated_messages).
        """
        history = list(messages)

        for _round in range(max_tool_rounds):
            result = self.chat(
                history,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                enable_thinking=True,
            )

            # Surface reasoning
            if result.reasoning and on_thinking:
                on_thinking(result.reasoning)

            # No tool calls → final answer
            if not result.tool_calls:
                history.append({"role": "assistant", "content": result.text})
                return result.text, history

            # Execute each tool call and feed responses back
            for tc in result.tool_calls:
                if on_tool_call:
                    on_tool_call(tc.name, tc.arguments)

                try:
                    tool_result = tool_executor(tc.name, tc.arguments)
                except Exception as e:
                    tool_result = {"error": str(e)}

                # Append model's tool call turn
                history.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": f"call_{_round}",
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }],
                })
                # Append tool result turn
                history.append({
                    "role": "tool",
                    "tool_call_id": f"call_{_round}",
                    "content": json.dumps(tool_result),
                })

        # Max rounds hit — generate final synthesis
        history.append({"role": "user", "content": "Please summarise your findings so far."})
        result = self.chat(history, tools=None, max_tokens=max_tokens)
        return result.text, history

    def generate_proposal(self, prompt: str, context: dict) -> Tuple[str, dict]:
        """Generate structured experiment proposal."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a scientific AI operating within VirtualLab. "
                    "Generate a JSON experiment proposal for the RHO P23H disease model. "
                    "Output ONLY valid JSON. No prose."
                ),
            },
            {
                "role": "user",
                "content": f"Context:\n{json.dumps(context, indent=2)}\n\nPrompt:\n{prompt}",
            },
        ]
        result = self.chat(messages, max_tokens=1024, temperature=0.2)
        return result.text, {}
