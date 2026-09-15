from PySide6.QtCore import QObject, Signal
from typing import Optional
from virtual_lab.gui.services.selection import ScientificSelection, SelectionKind

class WorkspaceState(QObject):
    activeExperimentChanged = Signal(str)
    activeBranchChanged = Signal(str)
    selectedObjectChanged = Signal(object)
    simulationTimeChanged = Signal(float)
    selectedEnsembleMemberChanged = Signal(int)
    resultChanged = Signal(object)
    evidenceSelectionChanged = Signal(object)
    contextChanged = Signal(str)

    def __init__(self):
        super().__init__()

        self._active_project_id: Optional[str] = None
        self._active_experiment_id: Optional[str] = None
        self._active_branch_id: Optional[str] = None

        self._selected_object: ScientificSelection = ScientificSelection(kind=SelectionKind.NONE)
        self._selected_compound: Optional[str] = None
        self._selected_evidence: Optional[str] = None

        self._simulation_time_h: float = 0.0
        self._selected_ensemble_member: Optional[int] = None

        self._current_result = None
        self._current_context_hash: Optional[str] = None

    @property
    def simulation_time_h(self) -> float:
        return self._simulation_time_h

    @simulation_time_h.setter
    def simulation_time_h(self, value: float):
        if self._simulation_time_h != value:
            self._simulation_time_h = value
            self.simulationTimeChanged.emit(value)

    @property
    def selected_object(self) -> ScientificSelection:
        return self._selected_object

    @selected_object.setter
    def selected_object(self, value: ScientificSelection):
        if self._selected_object != value:
            self._selected_object = value
            self.selectedObjectChanged.emit(value)

    @property
    def current_result(self):
        return self._current_result

    @current_result.setter
    def current_result(self, value):
        self._current_result = value
        self.resultChanged.emit(value)
        
    @property
    def active_experiment_id(self) -> Optional[str]:
        return self._active_experiment_id
        
    @active_experiment_id.setter
    def active_experiment_id(self, value: Optional[str]):
        if self._active_experiment_id != value:
            self._active_experiment_id = value
            self.activeExperimentChanged.emit(value)
