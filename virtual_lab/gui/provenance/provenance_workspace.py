import json
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QPlainTextEdit
from virtual_lab.gui.services.run_store import RunStore
class ProvenanceWorkspace(QWidget):
    def __init__(self,workspace,parent=None,ledger=None):
        super().__init__(parent);layout=QVBoxLayout(self)
        self.ledger=ledger;self.workspace=workspace
        self.status=QLabel();layout.addWidget(self.status)
        self.event_list=QListWidget();layout.addWidget(self.event_list)
        self.inspector=QPlainTextEdit();self.inspector.setReadOnly(True);layout.addWidget(self.inspector)
        self.events=[];self.event_list.currentRowChanged.connect(self.select)
        workspace.resultChanged.connect(self.refresh);self.refresh()
        workspace.observationCommitted.connect(self.refresh)
        workspace.observationStaged.connect(self.refresh)
        workspace.activeExperimentChanged.connect(self.refresh)
        workspace.activeProjectChanged.connect(self.refresh)
    def refresh(self,*_):
        self.event_list.clear();self.inspector.clear()
        try:
            store=RunStore();self.events=store.events()
            seen_ids={e["event_id"] for e in self.events}
            if self.ledger is not None:
                from virtual_lab.computational.artifacts import CompletedRun
                self.ledger.verify_chain()
                for row in self.ledger.conn.execute("SELECT * FROM ledger_events ORDER BY sequence"):
                    event=self.ledger._row_to_event(row).model_dump()
                    if event["event_id"] not in seen_ids:
                        self.events.append(event)
                        seen_ids.add(event["event_id"])
            from virtual_lab.domain.experiment_store import ExperimentStore
            database=ExperimentStore()
            try:
                project_id=self.workspace.active_project_id
                experiments={e['id'] for e in database.list_experiments() if project_id and e['project_id']==project_id}
                runs={o.session_id for exp in experiments for o in database.get_observations_for_experiment(exp)}
            finally:database.close()
            models={e['payload']['model_id'] for e in self.events if e['event_type']=='INTENT_MODEL_REGISTERED' and e['payload']['project_id']==project_id}
            runs.update(e['payload']['run_id'] for e in self.events if e['event_type']=='MS_DATASET_REGISTERED' and e['payload'].get('experiment_id') in experiments)
            def belongs(event):
                p=event['payload']
                return bool(project_id and (p.get('project_id')==project_id or p.get('experiment_id') in experiments or p.get('run_id') in runs or p.get('model_id') in models))
            self.events=[e for e in self.events if belongs(e)]
            for event in self.events:
                if event['event_type'] in ('COMPUTATIONAL_PREDICTION_RECORDED','SIMULATOR_AUDIT_RECORDED'):
                    from virtual_lab.computational.artifacts import CompletedRun
                    p=event['payload'];CompletedRun(p['artifact_path'],p['artifact_sha256']).read()
                elif event['event_type']=='SIMULATION_SAVED':
                    p=event['payload']
                    if p['file']!=p['sha256']+'.json':raise ValueError('Invalid simulation artifact reference')
                    import hashlib
                    if hashlib.sha256((store.root/p['file']).read_bytes()).hexdigest()!=p['sha256']:raise ValueError('Simulation artifact hash mismatch')
            imported_events = [e for e in self.events if e.get("event_type") == "STUDY_IMPORTED"]
            sim_events = [e for e in self.events if e.get("event_type") in ("SIMULATION_SAVED", "DESIGN_SAVED")]
            if imported_events and not sim_events:
                obs_count = sum(len(e.get("payload", {}).get("observations", [])) for e in imported_events)
                self.status.setText(
                    f"Imported study package verified ({obs_count} imported record(s) hash-checked; 0 local simulation runs)"
                )
            elif self.events:
                self.status.setText("Project-linked audit events and saved run artifacts verified; global chain checked")
            else:
                self.status.setText("No project-linked audit events selected")
            for e in self.events:self.event_list.addItem(f"{e['sequence']} • {e['event_type']} • {e['timestamp_utc']}")
        except Exception as exc:self.events=[];self.status.setText(f"INTEGRITY ERROR: {exc}")
    def select(self,row):
        if 0<=row<len(self.events):self.inspector.setPlainText(json.dumps(self.events[row],indent=2))
