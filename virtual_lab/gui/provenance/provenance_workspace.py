import json
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QPlainTextEdit
from virtual_lab.gui.services.run_store import RunStore
class ProvenanceWorkspace(QWidget):
    def __init__(self,workspace,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self)
        self.status=QLabel();layout.addWidget(self.status)
        self.event_list=QListWidget();layout.addWidget(self.event_list)
        self.inspector=QPlainTextEdit();self.inspector.setReadOnly(True);layout.addWidget(self.inspector)
        self.events=[];self.event_list.currentRowChanged.connect(self.select)
        workspace.resultChanged.connect(self.refresh);self.refresh()
    def refresh(self,*_):
        self.event_list.clear()
        try:
            store=RunStore();self.events=store.events();store.load_all()
            self.status.setText("Chain and referenced artifacts verified" if self.events else "No local run ledger yet")
            for e in self.events:self.event_list.addItem(f"{e['sequence']} • {e['event_type']} • {e['timestamp_utc']}")
        except Exception as exc:self.events=[];self.status.setText(f"INTEGRITY ERROR: {exc}")
    def select(self,row):
        if 0<=row<len(self.events):self.inspector.setPlainText(json.dumps(self.events[row],indent=2))
