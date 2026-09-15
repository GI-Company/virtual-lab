from PySide6.QtCore import QRunnable, QObject, Signal
import traceback
from google import genai
from virtual_lab.ai.providers.gemini import GeminiProvider
from virtual_lab.ai.context import ScientificContext
from virtual_lab.ai.tools import AGENT_TOOLS
import json

class AgentSignals(QObject):
    state_changed = Signal(str)
    message_received = Signal(str)
    tool_call_requested = Signal(object, str, dict) # tool_call_id, function_name, args
    finished = Signal()
    error = Signal(str)

class AgentWorker(QRunnable):
    def __init__(self, prompt: str, context: ScientificContext, chat_session=None):
        super().__init__()
        self.prompt = prompt
        self.context = context
        self.chat_session = chat_session
        self.signals = AgentSignals()
        self.provider = GeminiProvider()
        self._resume_tool_result = None
        
    def run(self):
        try:
            if not self.provider.client:
                raise RuntimeError("Gemini provider not configured.")
                
            self.signals.state_changed.emit("THINKING")
            
            # If we don't have a chat session, we create one
            if not self.chat_session:
                system_instruction = (
                    "You are a scientific AI Agent operating within VirtualLab. "
                    "You can propose experiments, execute them, and read results using the provided tools. "
                    f"Current epistemic context: Disease: {self.context.disease_model_id}, Compound: {self.context.compound_id}."
                )
                self.chat_session = self.provider.client.chats.create(
                    model="gemini-3.6-pro",
                    config=genai.types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=AGENT_TOOLS
                    )
                )
            
            # If we are resuming from a tool call, we send the tool response
            if self._resume_tool_result:
                response = self.chat_session.send_message(self._resume_tool_result)
            else:
                response = self.chat_session.send_message(self.prompt)
            
            # Process the response
            # Did the model call a tool?
            if response.function_calls:
                # We only handle the first function call for simplicity in Beta 1
                fc = response.function_calls[0]
                self.signals.state_changed.emit(f"REQUESTING TOOL: {fc.name}")
                
                # Convert args to dict
                args_dict = {k: v for k, v in fc.args.items()}
                
                # Yield to UI
                self.signals.tool_call_requested.emit(fc, fc.name, args_dict)
                return # Thread exits, UI must spawn a new worker with _resume_tool_result to continue
                
            # If no tool was called, it's a natural language message
            if response.text:
                self.signals.message_received.emit(response.text)
                
            self.signals.state_changed.emit("IDLE")
            self.signals.finished.emit()
            
        except Exception as exc:
            self.signals.state_changed.emit("FAILED")
            self.signals.error.emit(str(exc))
            traceback.print_exc()

    def set_tool_result(self, tool_call, result: dict):
        """Prepares the worker to resume with a tool result."""
        # google-genai requires us to send back a Part with a function_response
        self._resume_tool_result = genai.types.Part.from_function_response(
            name=tool_call.name,
            response=result
        )
