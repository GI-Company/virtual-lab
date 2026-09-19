from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QGroupBox, 
    QSplitter, QGridLayout, QFrame, QTextEdit, QStackedWidget, QListWidget, QListWidgetItem,
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem, QGraphicsRectItem
)
from PySide6.QtCore import Qt, QThread, QObject, Signal, Slot
from PySide6.QtGui import QColor, QPen, QBrush, QFont, QPainter
import json
import uuid

class ChatTextEdit(QTextEdit):
    returnPressed = Signal()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
            self.returnPressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class AgentRuntimeWorker(QObject):
    episode_started = Signal(str)
    hview_created = Signal(dict)
    reasoning_step_added = Signal(dict)
    tool_requested = Signal(str, dict)
    tool_completed = Signal(str, dict)
    metrics_updated = Signal(dict)
    proposal_created = Signal(dict)
    approval_required = Signal(object, dict) # episode, pending_actions
    answer_completed = Signal(str, list) # text, epistemic_tags
    episode_failed = Signal(str)
    
    # Streaming Signals
    stream_delta = Signal(str)
    stream_event = Signal(str, dict)
    
    def __init__(self, controller, experiment_id, hview_summary, auth_records, memory_revision, proj_dict):
        super().__init__()
        self.controller = controller
        self.experiment_id = experiment_id
        self.hview_summary = hview_summary
        self.auth_records = auth_records
        self.memory_revision = memory_revision
        self.proj_dict = proj_dict
        
    @Slot(str)
    def run_episode(self, user_request):
        try:
            self.episode_started.emit("Starting episode")
            episode = self.controller.run_episode(
                user_request, self.experiment_id, self.hview_summary, 
                self.auth_records, self.memory_revision, self.proj_dict,
                stream_callback=self._handle_stream
            )
            self._handle_termination(episode)
        except Exception as e:
            self.episode_failed.emit(str(e))
            
    @Slot(object, str, dict, dict)
    def resume_episode(self, episode, tool_name, tool_args, decision_result):
        try:
            episode = self.controller.resume_episode(
                episode, tool_name, tool_args, decision_result,
                self.hview_summary, self.auth_records, self.proj_dict,
                stream_callback=self._handle_stream
            )
            self._handle_termination(episode)
        except Exception as e:
            self.episode_failed.emit(str(e))
            
    def _handle_stream(self, event_type, payload):
        from virtual_lab.ai.agent.streaming import StreamEventType
        if event_type == StreamEventType.ANSWER_DELTA:
            self.stream_delta.emit(payload)
        elif event_type in (StreamEventType.TOOL_CALL_STARTED, StreamEventType.TOOL_CALL_COMPLETE, StreamEventType.PROPOSAL_COMPLETE):
            self.stream_event.emit(event_type.name, payload if isinstance(payload, dict) else {"raw": payload})
            
    def _handle_termination(self, episode):
        # Sync metrics
        if hasattr(self.controller, "model_backend") and self.controller.model_backend and hasattr(self.controller.model_backend, "last_metrics"):
            self.metrics_updated.emit(self.controller.model_backend.last_metrics)
            
        # Emit reasoning steps manually (in a full streaming version we'd use callbacks)
        for step in episode.reasoning_dag.steps:
            self.reasoning_step_added.emit({"type": step.step_type.name, "id": step.step_id, "tool": step.tool_name})
            
        if hasattr(episode, "pending_actions") and episode.pending_actions:
            self.approval_required.emit(episode, episode.pending_actions)
        elif episode.proposals and len(episode.proposals) > len(episode.human_decisions):
            # Pending proposal
            self.approval_required.emit(episode, {"proposal": "propose_experiment_branch"})
        elif episode.final_response_hash:
            # Re-read last tool result for final answer if needed, or assume answer complete
            ans = "Answer completed and verified."
            if episode.tool_results:
                last_res = episode.tool_results[-1]
                if last_res.get("tool") == "answer" or "text" in last_res.get("result", {}):
                    ans = str(last_res)
            # Find epistemic tags from authoritative records
            tags = [r.get("epistemic_state", "UNKNOWN") for r in self.auth_records]
            self.answer_completed.emit(ans, tags)
        else:
            self.episode_failed.emit(f"Terminated unexpectedly. Steps: {episode.step_count}")

class HVIEWGraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#0f172a")))
        
    def render_hview(self, projection_dict):
        self.scene.clear()
        nodes = projection_dict.get("nodes", [])
        edges = projection_dict.get("edges", [])
        
        node_items = {}
        for n in nodes:
            px, py = n["position"]["x"] * 20, n["position"]["y"] * 20
            r = n.get("size", 10.0)
            color = QColor(n.get("color", "white"))
            
            if n.get("shape") == "circle":
                item = QGraphicsEllipseItem(px - r, py - r, r*2, r*2)
            else:
                item = QGraphicsRectItem(px - r, py - r, r*2, r*2)
                
            item.setBrush(QBrush(color))
            item.setToolTip(f"ID: {n.get('render_id')}\nLabel: {n.get('label')}")
            self.scene.addItem(item)
            node_items[n["render_id"]] = (px, py)
            
            # Label
            if n.get("label"):
                txt = QGraphicsTextItem(n["label"])
                txt.setDefaultTextColor(QColor("white"))
                txt.setPos(px + r + 2, py - r - 2)
                self.scene.addItem(txt)
                
        for e in edges:
            if e["source"] in node_items and e["target"] in node_items:
                sx, sy = node_items[e["source"]]
                tx, ty = node_items[e["target"]]
                line = QGraphicsLineItem(sx, sy, tx, ty)
                line.setPen(QPen(QColor(e.get("color", "gray")), e.get("width", 2)))
                line.setZValue(-1) # Behind nodes
                self.scene.addItem(line)

class LocalResearchWorkspace(QWidget):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace_state = workspace
        self.controller = None
        
        # Thread lifecycle management
        self.agent_thread = None
        self.agent_worker = None
        
        main_layout = QVBoxLayout(self)
        
        # 1. LocalResearchStatusPanel (Header)
        self.status_panel = QFrame()
        self.status_panel.setStyleSheet("background-color: #1e293b; border-radius: 4px; padding: 5px;")
        status_layout = QHBoxLayout(self.status_panel)
        
        self.lbl_cert = QLabel("<b>Gemma 4 12B Unified</b><br/><span style='color: #22c55e;'>LOCAL<br/>MULTIMODAL FUNCTIONAL<br/>MASK SEMANTICS VERIFIED<br/>FULL MODEL NUMERIC PARITY: NOT RUN</span>")
        self.lbl_cert.setStyleSheet("color: #94a3b8;")
        status_layout.addWidget(self.lbl_cert)
        
        self.lbl_metrics = QLabel("Text: 0 | Image: 0 | Pos: 0 | Prefill: 0ms | Decode: 0 t/s | Mem: 0MB")
        self.lbl_metrics.setStyleSheet("color: #cbd5e1;")
        status_layout.addWidget(self.lbl_metrics)
        
        self.lbl_egress = QLabel("External AI egress: <span style='color: #ef4444;'>DISABLED</span><br/>Network retrieval: <span style='color: #ef4444;'>DISABLED</span>")
        status_layout.addWidget(self.lbl_egress)
        
        main_layout.addWidget(self.status_panel)
        
        # Splitter for main content
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side: Memory and HVIEW
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # 2. MemoryPanel
        self.memory_panel = QGroupBox("MEMORY PROVENANCE")
        self.memory_panel.setStyleSheet("color: #38bdf8;")
        mem_layout = QVBoxLayout(self.memory_panel)
        self.lbl_mem_info = QLabel("HVIEW ID: --\nSHA-256: --\nRevision: --\nNodes: 0 | Edges: 0")
        mem_layout.addWidget(self.lbl_mem_info)
        left_layout.addWidget(self.memory_panel)
        
        # 3. HypervoxelView
        self.hview = HVIEWGraphicsView()
        left_layout.addWidget(self.hview)
        
        splitter.addWidget(left_widget)
        
        # Right side: Trace, Answer, Approval
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 4. CognitiveTracePanel & GenesisTracePanel
        self.trace_panel = QGroupBox("COGNITIVE & GENESIS TRACE")
        trace_layout = QVBoxLayout(self.trace_panel)
        self.lst_trace = QListWidget()
        self.lst_trace.setStyleSheet("background-color: #0f172a; color: #94a3b8; font-family: monospace;")
        trace_layout.addWidget(self.lst_trace)
        right_layout.addWidget(self.trace_panel)
        
        # 5. EpistemicAnswerPanel
        self.answer_panel = QGroupBox("SCIENTIFIC ANSWER")
        ans_layout = QVBoxLayout(self.answer_panel)
        self.lbl_answer = QLabel("Awaiting query...")
        self.lbl_answer.setWordWrap(True)
        ans_layout.addWidget(self.lbl_answer)
        self.lbl_tags = QLabel("")
        self.lbl_tags.setStyleSheet("font-weight: bold; color: #fbbf24;")
        ans_layout.addWidget(self.lbl_tags)
        right_layout.addWidget(self.answer_panel)
        
        # 6. ProposalApprovalPanel
        self.approval_panel = QGroupBox("PENDING ACTION / PROPOSAL")
        self.approval_panel.setStyleSheet("QGroupBox { border: 2px solid #f59e0b; }")
        app_layout = QVBoxLayout(self.approval_panel)
        self.lbl_pending = QLabel()
        app_layout.addWidget(self.lbl_pending)
        
        btn_layout = QHBoxLayout()
        self.btn_approve = QPushButton("Approve")
        self.btn_reject = QPushButton("Reject")
        self.btn_approve.clicked.connect(self._on_approve)
        self.btn_reject.clicked.connect(self._on_reject)
        btn_layout.addWidget(self.btn_reject)
        btn_layout.addWidget(self.btn_approve)
        app_layout.addLayout(btn_layout)
        
        self.approval_panel.hide()
        right_layout.addWidget(self.approval_panel)
        
        # Prompt input
        prompt_layout = QHBoxLayout()
        self.txt_prompt = ChatTextEdit()
        self.txt_prompt.setMaximumHeight(60)
        self.txt_prompt.returnPressed.connect(self._on_send)
        self.btn_send = QPushButton("Send")
        self.btn_send.clicked.connect(self._on_send)
        prompt_layout.addWidget(self.txt_prompt)
        prompt_layout.addWidget(self.btn_send)
        right_layout.addLayout(prompt_layout)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([600, 800])
        main_layout.addWidget(splitter)
        
        self.pending_episode = None
        self.pending_tool_name = None
        self.pending_tool_args = None
        
        self.mock_proj = {}

    def set_hview(self, proj_dict: dict, memory_info: str):
        self.mock_proj = proj_dict
        self.lbl_mem_info.setText(memory_info)
        self.hview.render_hview(proj_dict)

    def _on_send(self):
        prompt = self.txt_prompt.toPlainText().strip()
        if not prompt or not self.controller: return
        
        self.txt_prompt.clear()
        self.lst_trace.clear()
        self.lbl_answer.setText("") # Clear previous answer
        self.lbl_tags.clear()
        self.approval_panel.hide()
        
        self.lst_trace.addItem("SYSTEM: Assembling context...")
        
        self._start_worker(prompt)

    def shutdown_agent_runtime(self):
        if self.agent_thread is not None and self.agent_thread.isRunning():
            self.lst_trace.addItem("SYSTEM: Requesting agent cancellation...")
            self.agent_thread.quit()
            if not self.agent_thread.wait(5000):
                self.lst_trace.addItem("SYSTEM: WARNING - Agent thread failed to stop within 5s")
                return False
            
        self.agent_worker = None
        self.agent_thread = None
        return True

    def closeEvent(self, event):
        if not self.shutdown_agent_runtime():
            # If it didn't shut down, maybe we force close anyway?
            pass
        super().closeEvent(event)

    def _start_worker(self, prompt=None):
        if self.agent_thread is not None and self.agent_thread.isRunning():
            self.lst_trace.addItem("SYSTEM: ERROR - An episode is already running. Please wait or cancel.")
            return
            
        self.shutdown_agent_runtime()
            
        auth_records = [{"store_kind": "EXPERIMENT", "entity_type": "PREDICTION", "entity_id": "yc-001", "epistemic_state": "SIMULATED"}]
        
        self.agent_worker = AgentRuntimeWorker(
            self.controller, "EXP-42", "HVIEW Summary", auth_records, 1, self.mock_proj
        )
        self.agent_thread = QThread(self)
        self.agent_worker.moveToThread(self.agent_thread)
        
        self.agent_worker.metrics_updated.connect(self._on_metrics)
        self.agent_worker.reasoning_step_added.connect(self._on_step)
        self.agent_worker.approval_required.connect(self._on_approval)
        self.agent_worker.answer_completed.connect(self._on_answer)
        self.agent_worker.episode_failed.connect(self._on_error)
        self.agent_worker.stream_delta.connect(self._on_stream_delta)
        self.agent_worker.stream_event.connect(self._on_stream_event)
        
        # Proper termination wiring
        self.agent_thread.finished.connect(self.agent_worker.deleteLater)
        self.agent_worker.answer_completed.connect(lambda text, tags: self.agent_thread.quit())
        self.agent_worker.episode_failed.connect(lambda err: self.agent_thread.quit())
        self.agent_worker.approval_required.connect(lambda ep, actions: self.agent_thread.quit())
        
        if prompt:
            self.agent_thread.started.connect(lambda: self.agent_worker.run_episode(prompt))
        
        self.agent_thread.start()
        
    def _resume_worker(self, decision_result):
        if self.agent_thread is not None and self.agent_thread.isRunning():
            self.lst_trace.addItem("SYSTEM: ERROR - Cannot resume, thread already running.")
            return
            
        self.shutdown_agent_runtime()
        
        auth_records = [{"store_kind": "EXPERIMENT", "entity_type": "PREDICTION", "entity_id": "yc-001", "epistemic_state": "SIMULATED"}]
        self.agent_worker = AgentRuntimeWorker(
            self.controller, "EXP-42", "HVIEW Summary", auth_records, 1, self.mock_proj
        )
        self.agent_thread = QThread(self)
        self.agent_worker.moveToThread(self.agent_thread)
        
        # Connect signals
        self.agent_worker.metrics_updated.connect(self._on_metrics)
        self.agent_worker.reasoning_step_added.connect(self._on_step)
        self.agent_worker.approval_required.connect(self._on_approval)
        self.agent_worker.answer_completed.connect(self._on_answer)
        self.agent_worker.episode_failed.connect(self._on_error)
        self.agent_worker.stream_delta.connect(self._on_stream_delta)
        self.agent_worker.stream_event.connect(self._on_stream_event)
        
        # Proper termination wiring
        self.agent_thread.finished.connect(self.agent_worker.deleteLater)
        self.agent_worker.answer_completed.connect(lambda text, tags: self.agent_thread.quit())
        self.agent_worker.episode_failed.connect(lambda err: self.agent_thread.quit())
        self.agent_worker.approval_required.connect(lambda ep, actions: self.agent_thread.quit())
        
        self.agent_thread.started.connect(lambda: self.agent_worker.resume_episode(
            self.pending_episode, self.pending_tool_name, self.pending_tool_args, decision_result
        ))
        
        self.agent_thread.start()
        self.approval_panel.hide()

    @Slot(dict)
    def _on_metrics(self, m):
        txt = f"Tokens: {m.get('text_tokens',0)} | Image: {m.get('image_soft_tokens',0)} | Pos: {m.get('total_sequence_positions',0)}<br/>"
        txt += f"Prefill: {m.get('prefill_latency',0):.2f}s | Decode: {m.get('decode_tokens_per_sec',0):.1f} t/s<br/>"
        txt += f"Sampler: {m.get('sampler','argmax')} (T={m.get('temperature',0.0)}) | Peak Mem: {m.get('peak_memory_bytes',0)/(1024**2):.1f}MB"
        self.lbl_metrics.setText(txt)

    @Slot(dict)
    def _on_step(self, step):
        self.lst_trace.addItem(f"DAG Step [{step['type']}]: {step['tool'] or step['id']}")
        self.lst_trace.scrollToBottom()

    @Slot(object, dict)
    def _on_approval(self, episode, pending_actions):
        self.pending_episode = episode
        # Get first pending action
        if pending_actions:
            k = list(pending_actions.keys())[0]
            v = pending_actions[k]
            if v == "propose_experiment_branch" or "propose" in k:
                self.approval_panel.setTitle("PENDING PROPOSAL")
                self.lbl_pending.setText(f"Proposed experiment branch\nStatus: PENDING\n\nID: {k}")
            else:
                self.approval_panel.setTitle("PENDING ACTION")
                self.lbl_pending.setText(f"Requested computational action\n{v}(...)\n\nID: {k}")
            
            self.pending_tool_name = v
            self.pending_tool_args = {"proposal_id": k}
            self.approval_panel.show()

    @Slot(str, list)
    def _on_answer(self, text, tags):
        self.lbl_tags.setText(" ".join([f"[{t}]" for t in tags]))
        
    @Slot(str)
    def _on_stream_delta(self, delta):
        current = self.lbl_answer.text()
        self.lbl_answer.setText(current + delta)
        
    @Slot(str, dict)
    def _on_stream_event(self, event_type, payload):
        if event_type == "TOOL_CALL_COMPLETE":
            self.lst_trace.addItem(f"STREAM: Tool Request Verified -> {payload.get('tool_name')}")
            self.lst_trace.scrollToBottom()
        elif event_type == "PROPOSAL_COMPLETE":
            self.lst_trace.addItem("STREAM: Proposal Generation Completed.")
            self.lst_trace.scrollToBottom()
        
    @Slot(str)
    def _on_error(self, err):
        self.lbl_answer.setText(f"<span style='color:#ef4444;'>Error: {err}</span>")

    def _on_approve(self):
        # We synthesize a decision result
        from virtual_lab.ai.agent.types import ProposalDecision, ProposalDecisionStatus
        dec = ProposalDecision(self.pending_tool_args.get("proposal_id", "unknown"), ProposalDecisionStatus.APPROVED, "Approved by Human", "now")
        res = {"status": "success", "decision": dec.decision.value}
        self.lst_trace.addItem(f"GENESIS EVENT: Human Approval Recorded -> {res}")
        self._resume_worker(res)

    def _on_reject(self):
        res = {"status": "rejected", "error": "Human rejected the action."}
        self.lst_trace.addItem(f"GENESIS EVENT: Human Rejection Recorded")
        self._resume_worker(res)
