from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QScrollArea, QGroupBox, QFormLayout, 
                               QSplitter, QGridLayout, QFrame, QTextEdit, QStackedWidget, QMessageBox, QComboBox)
from PySide6.QtCore import Qt, QThreadPool
import json

from virtual_lab.ai.providers.gemini import GeminiProvider
from virtual_lab.ai.providers.mlx_local import MLXLocalProvider
from virtual_lab.gui.ai.settings_dialog import SettingsDialog
from virtual_lab.ai.context import ScientificContext
from virtual_lab.ai.agent_loop import AgentWorker

class AIWorkbench(QWidget):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        
        self._mlx = None
        self.provider = None
        self.thread_pool = QThreadPool.globalInstance()
        self.chat_session = None
        
        main_layout = QVBoxLayout(self)
        
        # Header
        header = QHBoxLayout()
        lbl_title = QLabel("AGENTIC COPILOT")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #8b9bb4;")
        header.addWidget(lbl_title)
        
        # Mode Selector
        header.addSpacing(20)
        header.addWidget(QLabel("Mode:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Ask (Human in the Loop)", "Auto (Autonomous)", "Read-Only"])
        header.addWidget(self.cmb_mode)
        
        header.addStretch()
        
        self.lbl_provider_status = QLabel()
        self.btn_configure = QPushButton("Configure Provider")
        self.btn_configure.clicked.connect(self._open_settings)
        header.addWidget(self.lbl_provider_status)
        header.addWidget(self.btn_configure)
        main_layout.addLayout(header)
        
        self.stack = QStackedWidget()
        
        # Page 0: Not Configured
        self.page_not_configured = QWidget()
        pnc_layout = QVBoxLayout(self.page_not_configured)
        self.lbl_not_configured = QLabel()
        self.lbl_not_configured.setAlignment(Qt.AlignCenter)
        self.lbl_not_configured.setStyleSheet("font-size: 14px; color: #ef4444;")
        pnc_layout.addStretch()
        pnc_layout.addWidget(self.lbl_not_configured)
        pnc_layout.addStretch()
        self.stack.addWidget(self.page_not_configured)
        
        # Page 1: Agent Interface
        self.page_agent = QWidget()
        pa_layout = QVBoxLayout(self.page_agent)
        
        self.lbl_state = QLabel("IDLE")
        self.lbl_state.setAlignment(Qt.AlignCenter)
        self.lbl_state.setStyleSheet("color: #38bdf8; font-weight: bold;")
        pa_layout.addWidget(self.lbl_state)
        
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("background-color: #16202d; color: #94a3b8;")
        pa_layout.addWidget(self.chat_history)
        
        # Intercept UI for Tools
        self.tool_intercept = QGroupBox("Tool Call Intercept")
        self.tool_intercept.setStyleSheet("QGroupBox { border: 2px solid #f59e0b; margin-top: 1ex; }")
        ti_layout = QVBoxLayout(self.tool_intercept)
        self.lbl_tool_info = QLabel()
        self.lbl_tool_info.setWordWrap(True)
        ti_layout.addWidget(self.lbl_tool_info)
        
        ti_actions = QHBoxLayout()
        self.btn_allow = QPushButton("Allow")
        self.btn_allow.setObjectName("primary")
        self.btn_reject = QPushButton("Reject")
        self.btn_allow.clicked.connect(self._on_allow_tool)
        self.btn_reject.clicked.connect(self._on_reject_tool)
        ti_actions.addWidget(self.btn_reject)
        ti_actions.addWidget(self.btn_allow)
        ti_layout.addLayout(ti_actions)
        self.tool_intercept.hide()
        pa_layout.addWidget(self.tool_intercept)
        
        prompt_layout = QHBoxLayout()
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setPlaceholderText("Command the Agent...")
        self.txt_prompt.setMaximumHeight(80)
        prompt_layout.addWidget(self.txt_prompt)
        
        self.btn_generate = QPushButton("Send")
        self.btn_generate.setObjectName("primary")
        self.btn_generate.setMinimumHeight(80)
        self.btn_generate.clicked.connect(self._on_send)
        prompt_layout.addWidget(self.btn_generate)
        pa_layout.addLayout(prompt_layout)
        
        # Reasoning panel (hidden until model starts thinking)
        self.grp_reasoning = QGroupBox("Model Reasoning")
        self.grp_reasoning.setStyleSheet(
            "QGroupBox { border: 1px solid #334155; color: #64748b; font-size: 10px; margin-top: 1ex; }"
        )
        reasoning_layout = QVBoxLayout(self.grp_reasoning)
        self.txt_reasoning = QTextEdit()
        self.txt_reasoning.setReadOnly(True)
        self.txt_reasoning.setMaximumHeight(100)
        self.txt_reasoning.setStyleSheet(
            "background-color: #0f172a; color: #475569; font-size: 11px; font-style: italic;"
        )
        reasoning_layout.addWidget(self.txt_reasoning)
        self.grp_reasoning.hide()
        pa_layout.addWidget(self.grp_reasoning)
        
        self.stack.addWidget(self.page_agent)
        main_layout.addWidget(self.stack)
        
        self.current_tool_call = None
        self.current_tool_name = None
        self.current_tool_args = None
        
        self._update_provider_status()

    def _update_provider_status(self):
        # AIWorkbench is legacy and feature-gated. Do not initialize providers automatically.
        self.lbl_provider_status.setText("Legacy AIWorkbench  ● DORMANT")
        self.lbl_provider_status.setStyleSheet("color: #64748b; font-weight: bold;")
        self.lbl_not_configured.setText(
            "LEGACY AI COPILOT\n● DORMANT\n\n"
            "This component is feature-gated. Use Local Research Mode instead."
        )
        self.stack.setCurrentWidget(self.page_not_configured)

    def _open_settings(self):
        # Allow enabling if they explicitly go to settings? For now just open the dialog.
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._update_provider_status()

    def _on_send(self):
        prompt = self.txt_prompt.toPlainText().strip()
        if not prompt: return
        
        self.chat_history.append(f"<b>You:</b> {prompt}\n")
        self.txt_prompt.clear()
        
        self._start_agent_worker(prompt)

    def _start_agent_worker(self, prompt, resume_tool_call=None, resume_result=None):
        self.btn_generate.setEnabled(False)
        self.txt_prompt.setEnabled(False)
        
        context = ScientificContext(
            context_id="CTX-001",
            disease_model_id="rho_p23h",
            disease_model_hash="sha256:dummy",
            experiment_id="EXP-001",
            experiment_hash="sha256:dummy",
            state_schema=["time", "concentration"],
            state_constraints={},
            parameter_values={"ec50_um": 0.98},
            parameter_epistemics={},
            parameter_uncertainties={},
            exposure_model="default",
            compound_identity="YC-001",
            evidence_snapshot_hash="sha256:dummy",
            mechanism_graph_hash="sha256:dummy",
            simulation_backend="mock",
            numerical_validation="mock"
        )
        
        worker = AgentWorker(prompt, context, self.chat_session, self.controller)
        worker.signals.state_changed.connect(self._on_state)
        worker.signals.message_received.connect(self._on_message)
        worker.signals.reasoning_received.connect(self._on_reasoning)
        worker.signals.tool_executing.connect(self._on_tool_executing)
        worker.signals.tool_call_requested.connect(self._on_tool)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)
        
        if resume_tool_call and resume_result is not None:
            worker.set_tool_result(resume_tool_call, resume_result)
            
        self.thread_pool.start(worker)

    def _on_state(self, state_msg):
        self.lbl_state.setText(state_msg)

    def _on_reasoning(self, reasoning: str):
        self.grp_reasoning.show()
        self.txt_reasoning.setPlainText(reasoning)

    def _on_tool_executing(self, name: str, args: dict):
        self.chat_history.append(
            f"<span style='color: #f59e0b;'>[TOOL ▶ {name}]</span>\n"
        )

    def _on_error(self, err_msg):
        self.chat_history.append(f"<span style='color: #ef4444;'><b>System Error:</b> {err_msg}</span>\n")
        self._on_finished()

    def _on_message(self, msg):
        self.grp_reasoning.hide()
        self.chat_history.append(f"<b>Agent:</b> {msg}\n")
        
    def _on_finished(self):
        self.btn_generate.setEnabled(True)
        self.txt_prompt.setEnabled(True)

    def _on_tool(self, tool_call, name, args):
        # We need to save the session to resume it later
        # However, the worker can't pass back self.chat_session safely without a signal,
        # but since we pass `self.chat_session` into the worker, it mutates our ref directly.
        # Actually, if `self.chat_session` was None initially, we need to capture it.
        # For this prototype, we'll assume the chat session persists.
        
        self.current_tool_call = tool_call
        self.current_tool_name = name
        self.current_tool_args = args
        
        formatted_args = json.dumps(args, indent=2)
        info = f"<b>Agent requests to execute:</b> {name}\n<pre>{formatted_args}</pre>"
        self.lbl_tool_info.setText(info)
        
        mode = self.cmb_mode.currentText()
        if "Auto" in mode:
            # Execute automatically
            self.chat_history.append(f"<span style='color: #f59e0b;'>[AUTO-EXECUTING: {name}]</span>\n")
            self._execute_tool_and_resume()
        elif "Ask" in mode:
            # Show intercept UI
            self.tool_intercept.show()
            self.lbl_state.setText("WAITING FOR HUMAN APPROVAL")
        else:
            # Read Only
            self.chat_history.append(f"<span style='color: #ef4444;'>[TOOL REJECTED (Read-Only Mode): {name}]</span>\n")
            self._start_agent_worker("", self.current_tool_call, {"error": "Rejected by Read-Only mode"})
            
    def _on_allow_tool(self):
        self.tool_intercept.hide()
        self.chat_history.append(f"<span style='color: #22c55e;'>[HUMAN APPROVED: {self.current_tool_name}]</span>\n")
        self._execute_tool_and_resume()
        
    def _on_reject_tool(self):
        self.tool_intercept.hide()
        self.chat_history.append(f"<span style='color: #ef4444;'>[HUMAN REJECTED: {self.current_tool_name}]</span>\n")
        self._start_agent_worker("", self.current_tool_call, {"error": "Human rejected the execution."})

    def _execute_tool_and_resume(self):
        # This is where we wire to the actual VirtualLab backend and Ledger
        # For Beta 1, we simulate success and log to ledger
        result = {"status": "success", "message": f"Successfully executed {self.current_tool_name}"}
        
        # 4. Genesis Ledger Integration
        self._log_to_ledger(self.current_tool_name, self.current_tool_args)
        
        # Resume the loop
        self._start_agent_worker("", self.current_tool_call, result)

    def _log_to_ledger(self, tool_name, args):
        # We simulate the ledger API here
        # In the real app, this goes to workspace.ledger.append(..., Actor(type="AI", id="gemini"), ...)
        self.chat_history.append(f"<span style='color: #94a3b8;'><i>[Ledger entry created with ACTOR_TYPE=AI]</i></span>\n")
