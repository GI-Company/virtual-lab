import json
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QPlainTextEdit
from virtual_lab.gui.services.run_store import RunStore
class ProvenanceWorkspace(QWidget):
    def __init__(self,workspace,parent=None,ledger=None):
        super().__init__(parent);layout=QVBoxLayout(self)
        self.ledger=ledger
        self.status=QLabel();layout.addWidget(self.status)
        self.event_list=QListWidget();layout.addWidget(self.event_list)
        self.inspector=QPlainTextEdit();self.inspector.setReadOnly(True);layout.addWidget(self.inspector)
        self.events=[];self.event_list.currentRowChanged.connect(self.select)
        workspace.resultChanged.connect(self.refresh);self.refresh()
        workspace.observationCommitted.connect(self.refresh)
        workspace.observationStaged.connect(self.refresh)
    def refresh(self,*_):
        self.event_list.clear()
        try:
            store=RunStore();self.events=store.events();store.load_all()
            if self.ledger is not None:
                from virtual_lab.computational.artifacts import CompletedRun
                self.ledger.verify_chain()
                for row in self.ledger.conn.execute("SELECT * FROM ledger_events WHERE event_type = 'COMPUTATIONAL_PREDICTION_RECORDED' ORDER BY sequence"):
                    event=self.ledger._row_to_event(row).model_dump()
                    p=event["payload"]
                    CompletedRun(p["artifact_path"],p["artifact_sha256"]).read()
                    self.events.append(event)
            self.status.setText("Run chains and saved run artifacts verified" if self.events else "No local run ledger yet")
            for e in self.events:self.event_list.addItem(f"{e['sequence']} • {e['event_type']} • {e['timestamp_utc']}")
        except Exception as exc:self.events=[];self.status.setText(f"INTEGRITY ERROR: {exc}")
    def select(self,row):
        if 0<=row<len(self.events):self.inspector.setPlainText(json.dumps(self.events[row],indent=2))
