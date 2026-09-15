import numpy as np
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QGraphicsScene,QGraphicsView
from PySide6.QtGui import QColor,QBrush,QPen
class CellView(QWidget):
    def __init__(self,workspace,parent=None):
        super().__init__(parent);self.workspace=workspace;self.result=None
        layout=QVBoxLayout(self);label=QLabel('Mechanistic schematic • normalized ODE pools • no spatial cell simulation')
        label.setWordWrap(True);layout.addWidget(label)
        self.scene=QGraphicsScene();self.view=QGraphicsView(self.scene);layout.addWidget(self.view,1)
        self.note=QLabel('Run an experiment to animate its saved states using the shared timeline.');self.note.setWordWrap(True);layout.addWidget(self.note)
        workspace.resultChanged.connect(self.set_result);workspace.simulationTimeChanged.connect(self.render)
    def set_result(self,result):self.result=result;self.render(workspace_time=self.workspace.simulation_time_h)
    def render(self,workspace_time=0):
        if not self.result:return
        r=self.result;index=int(np.argmin(abs(np.asarray(r.times_h)-workspace_time)))
        values=r.summary_trajectory["median"][index];self.scene.clear()
        positions=[(0,40),(210,40),(420,40),(210,200),(420,200)]
        labels=['Folded pool','ER retained','Surface pool','Stress','Viability state']
        for a,b in [(0,1),(0,2),(1,3),(3,4)]:
            x,y=positions[a];xx,yy=positions[b];self.scene.addLine(x+70,y+35,xx+70,yy+35,QPen(QColor('#657d98'),2))
        for i,(x,y) in enumerate(positions):
            self.scene.addEllipse(x,y,145,85,QPen(QColor('#38bdf8'),2),QBrush(QColor('#18394e')))
            text=self.scene.addText(f'{labels[i]}\n{values[i]:.4g}');text.setDefaultTextColor(QColor('#e2e8f0'));text.setPos(x+10,y+15)
        self.note.setText(f"Saved checkpoint: {r.times_h[index]:.2f} h • treatment medians • assumed parameters\nConnections show model dependencies; geometry does not encode measured cellular positions.")
        from PySide6.QtCore import Qt
        self.view.fitInView(self.scene.itemsBoundingRect(),Qt.KeepAspectRatio)
