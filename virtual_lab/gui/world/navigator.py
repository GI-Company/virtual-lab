from PySide6.QtWidgets import QWidget,QVBoxLayout,QTreeWidget,QTreeWidgetItem
from PySide6.QtCore import Qt
class ScientificNavigator(QWidget):
    def __init__(self,controller,parent=None):
        super().__init__(parent);self.controller=controller;layout=QVBoxLayout(self)
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True);layout.addWidget(self.tree)
        for title,children in [('Disease Program: RHO P23H',[('Human P23H variant','P23H'),('RHO protein','Protein')]),
            ('Compounds',[('YC-001 • literature linked','YC-001'),('YC-054 • no linked evidence','YC-054')]),
            ('Model parameters',[(x,'parameter:'+x) for x in ('k_mis','k_traffic','k_ERAD')]),
            ('Views',[(x,x) for x in ('Molecular','Protein Context','Cellular','Tissue')])]:
            root=QTreeWidgetItem(self.tree,[title])
            for text,key in children:
                item=QTreeWidgetItem(root,[text]);item.setData(0,Qt.UserRole,key)
            root.setExpanded(True)
        self.tree.itemClicked.connect(lambda item,col:controller.handle_navigator_click(item.data(0,Qt.UserRole) or ''))
