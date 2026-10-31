"""Headless research context. Client views do not own scientific calculations."""
from __future__ import annotations
import logging
from typing import Protocol, Any
from virtual_lab.application.selection import ScientificSelection, SelectionKind

log = logging.getLogger(__name__)


class Event:
    """Synchronous local notifications; durable changes are recorded in Genesis."""
    def __init__(self):
        self._subscribers = []

    def connect(self, callback):
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def disconnect(self, callback):
        self._subscribers.remove(callback)

    def emit(self, *args):
        for callback in tuple(self._subscribers):
            try:
                callback(*args)
            except Exception:
                # A view notification must not turn a committed write into a failed command.
                log.warning('A research view subscriber failed', exc_info=False)


class ResearchContext(Protocol):
    _active_project_id: str | None
    active_experiment: Any
    current_result: Any
    selected_object: ScientificSelection
    activeProjectChanged: Any
    calibrationResultChanged: Any
    biologicalResultChanged: Any
    validationResultChanged: Any
    evidenceSelectionChanged: Any
    observationCommitted: Any


class HeadlessWorkspace:
    def __init__(self):
        for name in ('activeProjectChanged','activeExperimentChanged','resultChanged',
                     'calibrationResultChanged','biologicalResultChanged','validationResultChanged',
                     'evidenceSelectionChanged','observationCommitted','observationStaged','aiStateChanged'):
            setattr(self, name, Event())
        self._active_project_id = None
        self._active_experiment = None
        self._current_result = None
        self._selected_compound = None
        self._selected_evidence = None
        self.selected_object = ScientificSelection(kind=SelectionKind.NONE)
        self.ai_state = 'off'

    @property
    def active_project_id(self):
        return self._active_project_id

    @property
    def active_experiment(self):
        return self._active_experiment

    @active_experiment.setter
    def active_experiment(self, value):
        self._active_experiment = value
        self.activeExperimentChanged.emit(value.id if value else '')

    @property
    def current_result(self):
        return self._current_result

    @current_result.setter
    def current_result(self, value):
        self._current_result = value
        self.resultChanged.emit(value)
