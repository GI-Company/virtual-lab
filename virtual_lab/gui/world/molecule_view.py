import json
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                               QPushButton, QLabel, QComboBox, QFormLayout, QGroupBox)
from virtual_lab.gui.services.selection import SelectionKind
from virtual_lab.gui.services.molecule_design import build_design
from virtual_lab.gui.services.run_store import RunStore
from virtual_lab.gui.widgets.badges import EpistemicBadge

class MoleculeView(QWidget):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.design = None
        self.ready = False
        self.workspace = workspace
        self.assets = Path(__file__).parents[1] / 'assets'
        self.records = json.loads((self.assets / 'compounds.json').read_text())
        
        layout = QVBoxLayout(self)
        
        # Selector
        self.selector = QComboBox()
        self.valid = {r['compound_name']: r for r in self.records if r['identity_status'] == 'model_eligible' and r['smiles']}
        self.selector.addItems(list(self.valid))
        layout.addWidget(self.selector)
        
        # SMILES
        self.smiles = QLineEdit()
        self.smiles.setPlaceholderText('Edit SMILES to design a molecule')
        layout.addWidget(self.smiles)
        
        # Build Button
        self.generate = QPushButton('Build Molecule')
        self.generate.setObjectName("primary")
        layout.addWidget(self.generate)
        
        # Details Form
        self.details_group = QGroupBox("Properties")
        form = QFormLayout(self.details_group)
        self.lbl_formula = QLabel()
        self.lbl_mw = QLabel()
        self.lbl_atoms = QLabel()
        
        epistemic_layout = QVBoxLayout()
        epistemic_layout.addWidget(EpistemicBadge("2D identity: DERIVED"))
        epistemic_layout.addWidget(EpistemicBadge("3D conformer: CALCULATED"))
        epistemic_layout.addWidget(EpistemicBadge("binding pose: NOT AVAILABLE"))
        self.lbl_conformer = QWidget()
        self.lbl_conformer.setLayout(epistemic_layout)
        
        form.addRow("Formula", self.lbl_formula)
        form.addRow("MW", self.lbl_mw)
        form.addRow("Atoms", self.lbl_atoms)
        form.addRow("Epistemic Status", self.lbl_conformer)
        self.details_group.setVisible(False)
        layout.addWidget(self.details_group)
        
        # Viewer
        self.view = QWebEngineView()
        self.channel = QWebChannel(self.view)
        self.view.page().setWebChannel(self.channel)
        self.view.loadFinished.connect(self.loaded)
        self.view.setUrl(QUrl.fromLocalFile(str(self.assets / 'viewer.html')))
        layout.addWidget(self.view, 1)
        
        # Add to experiment / Save
        self.save = QPushButton('Add to Experiment')
        self.save.setEnabled(False)
        layout.addWidget(self.save)
        
        self.selector.currentTextChanged.connect(self.choose)
        self.choose(self.selector.currentText())
        
        self.generate.clicked.connect(self.build)
        self.save.clicked.connect(self.persist)
        self.smiles.textChanged.connect(self.invalidate)
        workspace.selectedObjectChanged.connect(self.selected)

    def loaded(self, ok):
        self.ready = ok

    def invalidate(self):
        self.design = None
        self.save.setEnabled(False)
        self.details_group.setVisible(False)

    def choose(self, name):
        if name in self.valid:
            self.smiles.setText(self.valid[name]['smiles'])
            self.invalidate()

    def selected(self, selection):
        if selection.kind == SelectionKind.COMPOUND:
            if selection.compound_id in self.valid:
                self.selector.setCurrentText(selection.compound_id)

    def build(self):
        try:
            self.design = build_design(self.smiles.text())
            d = self.design
            self.save.setEnabled(True)
            self.details_group.setVisible(True)
            
            self.lbl_formula.setText(d['formula'])
            self.lbl_mw.setText(f"{d['molecular_weight']:.2f}")
            self.lbl_atoms.setText(f"{d['sdf'].split('V2000')[1].strip().split()[0]} atoms (approx)")
            
            if self.ready:
                self.view.page().runJavaScript('loadMolecule(' + json.dumps(d['sdf']) + ');')
        except Exception as exc:
            self.invalidate()

    def persist(self):
        if self.design:
            try:
                RunStore().save_design(self.design)
                self.save.setText('Added to Experiment!')
            except Exception as exc:
                pass
