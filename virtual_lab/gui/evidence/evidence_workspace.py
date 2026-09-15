from html import escape
from PySide6.QtWidgets import QWidget,QVBoxLayout,QListWidget,QTextBrowser,QPushButton,QLabel
from virtual_lab.gui.services.evidence_store import EvidenceStore
class EvidenceWorkspace(QWidget):
    def __init__(self,workspace,parent=None):
        super().__init__(parent);self.store=EvidenceStore();self.records=[]
        layout=QVBoxLayout(self);layout.addWidget(QLabel("Curated source-linked claims • counts are claims, not independent experiments"))
        show=QPushButton("Show all evidence");show.clicked.connect(lambda:self.filter(None));layout.addWidget(show)
        self.record_list=QListWidget();layout.addWidget(self.record_list)
        self.inspector=QTextBrowser();self.inspector.setOpenExternalLinks(True);layout.addWidget(self.inspector)
        self.record_list.currentRowChanged.connect(self.select)
        workspace.evidenceSelectionChanged.connect(self.filter);self.filter(None)
    def filter(self,selection):
        self.record_list.clear();self.records=self.store.records_for_selection(selection)
        for r in self.records:self.record_list.addItem(r['id'].replace('_',' '))
        self.inspector.setPlainText("No linked evidence for this selection." if not self.records else "Select a claim to inspect its original source.")
        if self.records:self.record_list.setCurrentRow(0)
    def select(self,row):
        if 0<=row<len(self.records):
            r=self.records[row]
            self.inspector.setHtml(f"<h3>CURATED LITERATURE CLAIM</h3><p>{escape(r['claim'])}</p><p>Source type: {escape(r['source_type'])}</p><a href='{escape(r['source'],quote=True)}'>Open original source</a><p>This citation does not validate the ODE parameters or establish human efficacy.</p>")
