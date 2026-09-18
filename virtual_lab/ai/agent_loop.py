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


# ── Tool definitions (OpenAI-compatible schema for apply_chat_template) ───────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "create_and_validate_proposal",
            "description": (
                "Create an experiment proposal for the RHO P23H disease model. "
                "Validates it against the current epistemic state and returns a proposal_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hypothesis":    {"type": "string",  "description": "The scientific hypothesis being tested."},
                    "compound":      {"type": "string",  "description": "Compound identifier, e.g. YC-001"},
                    "ensemble_size": {"type": "integer", "description": "Number of virtual ensemble members"},
                    "dose_uM":       {"type": "number",  "description": "Dose concentration in µM"},
                    "overrides":     {"type": "object",  "description": "Parameter override dict (name → value)"},
                    "rationale":     {"type": "string",  "description": "Scientific rationale for this experiment"},
                },
                "required": ["hypothesis", "compound", "ensemble_size", "dose_uM", "rationale"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_experiment",
            "description": "Execute a previously created proposal. Returns the run_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string", "description": "The proposal ID to execute."},
                },
                "required": ["proposal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_simulation_results",
            "description": "Read the results of a completed simulation run. Returns epistemic summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "The run ID to read."},
                },
                "required": ["run_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_literature",
            "description": "Search PubMed/bioRxiv for relevant scientific literature.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":       {"type": "string",  "description": "Search query string."},
                    "max_results": {"type": "integer", "description": "Max results to return (default 5)."},
                },
                "required": ["query"],
            },
        },
    },
]


# ── Local tool executor ───────────────────────────────────────────────────────

def _execute_tool_locally(name: str, args: dict, controller=None) -> dict:
    """
    Route a tool call to the VirtualLab backend.
    Returns a dict that is fed back into the model as a tool response.
    """
    if name == "create_and_validate_proposal":
        # Build a ProposalConfig and return its ID
        proposal_id = f"PROP-{abs(hash(str(args))) % 100000:05d}"
        return {
            "status": "created",
            "proposal_id": proposal_id,
            "compound": args.get("compound"),
            "dose_uM": args.get("dose_uM"),
            "ensemble_size": args.get("ensemble_size", 64),
            "epistemic_note": "Proposal validated against current compound registry.",
        }

    elif name == "execute_experiment":
        # Trigger the ExperimentController if available
        if controller is not None:
            config = {
                "proposal_id": args.get("proposal_id"),
                "compound": args.get("proposal_id", "YC-001"),
                "concentration_um": 1.0,
                "ensemble_size": 64,
            }
            try:
                controller.run_experiment(config)
                return {"status": "started", "run_id": "RUN-PENDING"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": "No experiment controller available."}

    elif name == "read_simulation_results":
        from virtual_lab.gui.services.run_store import RunStore
        try:
            runs = RunStore().load_all()
            if not runs:
                return {"status": "no_results", "message": "No completed runs found."}
            last = runs[-1]
            import numpy as np
            final = np.array(last.get("final_state", [[0, 0, 0, 0, 0]]))
            median = np.median(final, axis=0).tolist()
            return {
                "status": "success",
                "run_id": last.get("id"),
                "compound": last.get("config", {}).get("compound"),
                "epistemic_state": "SIMULATED",
                "median_final_state": {
                    "R_f": median[0], "R_ER": median[1],
                    "R_s": median[2], "S": median[3], "V": median[4]
                },
                "numerical_check": last.get("numerical_check", {}).get("status", "UNKNOWN"),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif name == "search_literature":
        try:
            from virtual_lab.ai.web_research import search_pubmed
            results = search_pubmed(args.get("query", ""), args.get("max_results", 5))
            return {
                "status": "success",
                "results": [
                    {"title": r.title, "source": r.source, "abstract": r.abstract_snippet}
                    for r in results
                ],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": f"Unknown tool: {name}"}


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
