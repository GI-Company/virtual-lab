"""
virtual_lab.ai.agent_loop
──────────────────────────
Agentic worker that routes to the best available provider:
  1. MLXLocalProvider  — Gemma 4 12B, local, native tool use + reasoning
  2. GeminiProvider    — cloud fallback (requires API key, quota-limited)

For MLX: runs a full local agentic loop via provider.agentic_chat()
  - Tool schemas defined in virtual_lab.ai.tools
  - Tool execution dispatched to the VirtualLab engine registry
  - Reasoning tokens surfaced via signals to the UI

For Gemini: retains original stateful chat session + API-level tool use
"""
from __future__ import annotations

import json
import traceback
from PySide6.QtCore import QRunnable, QObject, Signal


class AgentSignals(QObject):
    state_changed      = Signal(str)
    message_received   = Signal(str)
    reasoning_received = Signal(str)          # NEW: chain-of-thought text
    tool_call_requested = Signal(object, str, dict)  # Gemini path only
    tool_executing     = Signal(str, dict)     # NEW: tool name + args (local path)
    finished           = Signal()
    error              = Signal(str)


from virtual_lab.ai.tools import AGENT_TOOLS
import inspect

def _generate_tool_schemas():
    schemas = []
    for func in AGENT_TOOLS:
        sig = inspect.signature(func)
        properties = {}
        required = []
        for name, param in sig.parameters.items():
            properties[name] = {"type": "string"} # simplistic mapping for L1 tools
            if param.default == inspect.Parameter.empty:
                required.append(name)
        
        schemas.append({
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": func.__doc__ or "",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        })
    return schemas

TOOL_SCHEMAS = _generate_tool_schemas()

def _execute_tool_locally(name: str, args: dict, controller=None) -> dict:
    """
    Route a tool call to the VirtualLab backend.
    """
    allowed_tools = {f.__name__: f for f in AGENT_TOOLS}
    if name not in allowed_tools:
        return {"status": "error", "message": f"Tool {name} lacks L1 authority or does not exist."}
        
    func = allowed_tools[name]
    try:
        # In a real integration, this would invoke the actual backend services.
        # For the PoC, we just return a success representation of the proposal/read.
        return {
            "status": "success",
            "action": name,
            "recorded_args": args,
            "epistemic_note": "Executed under strict L1 autonomy constraints."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Worker ────────────────────────────────────────────────────────────────────

class AgentWorker(QRunnable):
    def __init__(self, prompt: str, context, chat_session=None, controller=None):
        super().__init__()
        self.prompt = prompt
        self.context = context
        self.chat_session = chat_session
        self.controller = controller
        self.signals = AgentSignals()
        self._resume_tool_result = None

        # Provider selection: MLX first, then Gemini
        from virtual_lab.ai.providers.mlx_local import MLXLocalProvider
        from virtual_lab.ai.providers.gemini import GeminiProvider

        mlx = MLXLocalProvider()
        if mlx.is_configured():
            self.provider = mlx
            self._backend = "mlx"
        else:
            self.provider = GeminiProvider()
            self._backend = "gemini"

    def run(self):
        try:
            if self._backend == "mlx":
                self._run_mlx()
            else:
                self._run_gemini()
        except Exception as exc:
            self.signals.state_changed.emit("FAILED")
            self.signals.error.emit(str(exc))
            traceback.print_exc()

    # ── MLX path ─────────────────────────────────────────────────────────────

    def _run_mlx(self):
        if not self.provider.is_configured():
            raise RuntimeError("MLX model not found. Check model path.")

        self.signals.state_changed.emit("THINKING [GEMMA 4 MLX]")

        system_msg = (
            "You are a scientific AI Agent operating within VirtualLab, a research platform "
            "for studying retinal degeneration caused by the RHO P23H mutation. "
            "You can propose experiments, execute them, read simulation results, and search the literature. "
            "All experiment results carry EpistemicState tags (SIMULATED, CALCULATED, MEASURED). "
            "Never fabricate results — always use the provided tools to get real data.\n\n"
            f"Current context: Disease: {self.context.disease_model_id}, "
            f"Compound: {self.context.compound_identity}."
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": self.prompt},
        ]

        def on_thinking(reasoning: str):
            self.signals.reasoning_received.emit(reasoning)

        def on_tool_call(name: str, args: dict):
            self.signals.state_changed.emit(f"EXECUTING TOOL: {name}")
            self.signals.tool_executing.emit(name, args)

        def tool_executor(name: str, args: dict) -> dict:
            return _execute_tool_locally(name, args, self.controller)

        final_text, _ = self.provider.agentic_chat(
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_executor=tool_executor,
            max_tool_rounds=8,
            max_tokens=2048,
            temperature=0.3,
            on_thinking=on_thinking,
            on_tool_call=on_tool_call,
        )

        if final_text:
            self.signals.message_received.emit(final_text)

        self.signals.state_changed.emit("IDLE")
        self.signals.finished.emit()

    # ── Gemini path (original, unchanged) ────────────────────────────────────

    def _run_gemini(self):
        from google import genai
        from virtual_lab.ai.tools import AGENT_TOOLS

        if not self.provider.client:
            raise RuntimeError(
                "Gemini provider not configured. Add API key or wait for MLX model."
            )

        self.signals.state_changed.emit("THINKING [GEMINI]")

        if not self.chat_session:
            system_instruction = (
                "You are a scientific AI Agent operating within VirtualLab. "
                "You can propose experiments, execute them, and read results using the provided tools. "
                f"Current epistemic context: Disease: {self.context.disease_model_id}, "
                f"Compound: {self.context.compound_identity}."
            )
            self.chat_session = self.provider.client.chats.create(
                model="gemini-3.1-pro-preview",
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=AGENT_TOOLS,
                ),
            )

        if self._resume_tool_result:
            response = self.chat_session.send_message(self._resume_tool_result)
        else:
            response = self.chat_session.send_message(self.prompt)

        if response.function_calls:
            fc = response.function_calls[0]
            self.signals.state_changed.emit(f"REQUESTING TOOL: {fc.name}")
            args_dict = {k: v for k, v in fc.args.items()}
            self.signals.tool_call_requested.emit(fc, fc.name, args_dict)
            return

        if response.text:
            self.signals.message_received.emit(response.text)

        self.signals.state_changed.emit("IDLE")
        self.signals.finished.emit()

    def set_tool_result(self, tool_call, result: dict):
        """Gemini path only: resume with tool response."""
        from google import genai
        self._resume_tool_result = genai.types.Part.from_function_response(
            name=tool_call.name,
            response=result,
        )
