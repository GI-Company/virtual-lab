"""Dedicated offline pilot workspace using VirtualLab's desktop and study services."""
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.core.paths import app_data_dir
from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.gui.shell.theme import get_stylesheet
from virtual_lab.gui.projects_workspace import ProjectsWorkspace
from virtual_lab.gui.ms_pilot_workspace import MSPilotWorkspace
from virtual_lab.gui.shell.layout import make_workspace_scrollable


class MSPilotWindow(QMainWindow):
    def __init__(self, *, profile='research'):
        super().__init__()
        self.presentation_profile=profile
        from virtual_lab.pilots.lease import WorkspaceLease
        self._workspace_lease = WorkspaceLease(app_data_dir())
        lease = self._workspace_lease
        self.destroyed.connect(lambda: lease.close())
        try:
            self._initialize()
        except BaseException:
            if hasattr(self, 'projects'):
                self.projects.service.store.close()
            if hasattr(self, 'ledger'):
                self.ledger.conn.close()
            lease.close()
            raise

    def _initialize(self):
        self.setWindowTitle('VirtualLab | MS Workflow Pilot | Local')
        self.resize(1280, 900)
        self.setMinimumSize(800, 600)
        self.setStyleSheet(get_stylesheet())
        self.workspace = WorkspaceState()
        root = app_data_dir()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.ledger = GenesisLedger(str(root/'genesis.db'))
        self.projects = ProjectsWorkspace(self.workspace, self.ledger, restore=False)
        self.ms_pilot = MSPilotWorkspace(self.workspace, self.projects.service, lease=self._workspace_lease)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.projects, 'Projects')
        self.tabs.addTab(self.ms_pilot, 'MS Workflow')
        from virtual_lab.gui.intent_workspace import IntentWorkspace
        self.intent_panel = IntentWorkspace(self.workspace, self.projects.service, lease=self._workspace_lease)
        self.tabs.addTab(self.intent_panel, 'INTENT (experimental)')
        from virtual_lab.gui.provenance.provenance_workspace import ProvenanceWorkspace
        self.provenance=ProvenanceWorkspace(self.workspace,ledger=self.ledger)
        self.tabs.addTab(self.provenance,'Provenance')
        for index in range(self.tabs.count()):
            make_workspace_scrollable(self.tabs.widget(index))
        from virtual_lab.gui.shell.research_navigation import ResearchNavigation
        self.navigation=ResearchNavigation(self.workspace,self.projects.service,self.tabs,
            {'projects':self.projects,'ms_workflow':self.ms_pilot,'intent':self.intent_panel,'provenance':self.provenance},
            profile=self.presentation_profile,can_switch=lambda:not self.intent_panel.busy)
        self.setCentralWidget(self.navigation)

    def closeEvent(self, event):
        if self.intent_panel.busy:
            self.intent_panel.cancel()
            event.ignore()
            return
        self.projects.service.store.close()
        self.ledger.conn.close()
        self._workspace_lease.close()
        super().closeEvent(event)


def main():
    import argparse
    parser=argparse.ArgumentParser(description='VirtualLab offline MS research workstation')
    parser.add_argument('--profile',choices=('research','academia'),default='research')
    args=parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv)
    window = MSPilotWindow(profile=args.profile)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
