from PySide6.QtCore import QRunnable, QObject, Signal
import traceback
from virtual_lab.ai.proposal_service import ProposalService
from virtual_lab.ai.context import ScientificContext

class ProposalWorkerSignals(QObject):
    state_changed = Signal(str) # IDLE, RESEARCHING, GENERATING, PARSING, VALIDATING, READY, FAILED
    finished = Signal(object)   # ProposalViewModel
    error = Signal(str)         # Error message

class ProposalWorker(QRunnable):
    def __init__(self, prompt: str, context: ScientificContext):
        super().__init__()
        self.prompt = prompt
        self.context = context
        self.signals = ProposalWorkerSignals()
        self.service = ProposalService()
        
    def run(self):
        try:
            self.signals.state_changed.emit("RESEARCHING & GENERATING")
            # The service currently does this in one go. If we split Path B later, we can emit separate signals.
            proposal_view_model = self.service.generate_and_validate(self.prompt, self.context)
            
            self.signals.state_changed.emit("READY")
            self.signals.finished.emit(proposal_view_model)
            
        except Exception as exc:
            self.signals.state_changed.emit("FAILED")
            self.signals.error.emit(str(exc))
            traceback.print_exc()
