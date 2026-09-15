import json
from pathlib import Path
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl,QObject,Slot
class MolstarBackend(QObject):
    def __init__(self,controller):super().__init__();self.controller=controller
    @Slot(str,int,str,int,str)
    def on_residue_clicked(self,structure_id,model_id,chain_id,residue_number,insertion_code):
        self.controller.handle_structure_click(structure_id,model_id,chain_id,residue_number,insertion_code)
class ProteinView(QWidget):
    def __init__(self,workspace,controller,parent=None):
        super().__init__(parent);self.workspace=workspace;self.controller=controller
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.label=QLabel('1U19 • BOVINE WILD TYPE • human P23H is a separate variant context • no YC-001 pose')
        self.label.setWordWrap(True);layout.addWidget(self.label)
        self.web_view=QWebEngineView();layout.addWidget(self.web_view,1)
        self.channel=QWebChannel(self.web_view);self.backend=MolstarBackend(controller)
        self.channel.registerObject('backend',self.backend);self.web_view.page().setWebChannel(self.channel)
        self.assets=Path(__file__).parents[1]/'assets';self.pending=None;self.loaded=False
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.web_view.setUrl(QUrl.fromLocalFile(str(self.assets/'viewer.html')))
        controller.focusRequested.connect(self.focus)
    def _on_load_finished(self,ok):
        self.loaded=ok
        if not ok:self.label.setText('Local viewer failed to load');return
        url=QUrl.fromLocalFile(str(self.assets/'1u19.pdb')).toString()
        self.web_view.page().runJavaScript('loadStructure('+json.dumps(url)+');')
        if self.pending:self.focus(self.pending)
    def focus(self,ref):
        self.pending=ref
        if self.loaded:self.web_view.page().runJavaScript('focusResidue('+json.dumps(ref)+');')
