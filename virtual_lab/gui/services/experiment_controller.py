import threading
from PySide6.QtCore import QObject, Signal, Slot, QThreadPool, QRunnable
from virtual_lab.gui.services.simulation_runner import run_simulation, RunConfig, RunCancelled
from virtual_lab.gui.services.run_store import RunStore

class WorkerSignals(QObject):
    progress=Signal(int)
    result=Signal(object)
    error=Signal(str)
    cancelled=Signal()

class SimulationWorker(QRunnable):
    def __init__(self, config):
        super().__init__()
        self.config=config
        self.signals=WorkerSignals()
        self.stop=threading.Event()
    def run(self):
        try:
            result=run_simulation(self.config,self.signals.progress.emit,self.stop.is_set)
            self.signals.result.emit(result)
        except RunCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")

class ExperimentController(QObject):
    runStarted=Signal()
    runProgress=Signal(int)
    runFinished=Signal(object)
    runFailed=Signal(str)
    runCancelled=Signal()
    def __init__(self,workspace):
        super().__init__(workspace)
        self.workspace=workspace
        self.worker=None
        self.store=RunStore()
    @Slot(dict)
    def run_experiment(self,config):
        if self.worker is not None: return
        try:
            cfg=RunConfig(**config);cfg.validate()
        except (TypeError,ValueError) as exc:
            self.runFailed.emit(str(exc));return
        self.worker=SimulationWorker(cfg)
        self.worker.signals.progress.connect(self.runProgress)
        self.worker.signals.result.connect(self._complete)
        self.worker.signals.error.connect(self._failed)
        self.worker.signals.cancelled.connect(self._cancelled)
        self.runStarted.emit()
        QThreadPool.globalInstance().start(self.worker)
    @Slot()
    def cancel(self):
        if self.worker: self.worker.stop.set()
    @Slot(object)
    def _complete(self,result):
        if self.worker and self.worker.stop.is_set():
            self._cancelled();return
        self.worker=None
        try:
            self.store.save(result)
        except Exception as exc:
            self.runFailed.emit(f"Computed but could not save result: {exc}");return
            
        from virtual_lab.gui.services.simulation_result import SimulationResult
        sim_result = SimulationResult.from_dict(result)
        
        from virtual_lab.domain.assemblers import simulation_result_to_observation
        from virtual_lab.domain.experiment_store import ExperimentStore
        
        active_exp = self.workspace.active_experiment
        exp_id_for_obs = active_exp.id if active_exp else ""
        obs = simulation_result_to_observation(result, exp_id_for_obs)
        
        db = ExperimentStore()
        if active_exp:
            active_exp.attach_observation(obs)
            db.save_observation(obs)
            self.workspace.observationCommitted.emit(obs)
        else:
            db.stage_observation(obs)
            self.workspace.observationStaged.emit(obs)
        
        self.workspace.current_result=sim_result
        self.runFinished.emit(sim_result)
    @Slot(str)
    def _failed(self,message):
        self.worker=None;self.runFailed.emit(message)
    @Slot()
    def _cancelled(self):
        self.worker=None;self.runCancelled.emit()
