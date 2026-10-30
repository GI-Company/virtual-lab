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
    def __init__(self):
        super().__init__()
        self.setWindowTitle('VirtualLab | MS Workflow Pilot | Local')
        self.resize(1280, 900)
        self.setMinimumSize(800, 600)
        self.setStyleSheet(get_stylesheet())
        self.workspace = WorkspaceState()
        root = app_data_dir()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.ledger = GenesisLedger(str(root/'genesis.db'))
        self.projects = ProjectsWorkspace(self.workspace, self.ledger)
        self.ms_pilot = MSPilotWorkspace(self.workspace, self.projects.service)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.projects, 'Projects')
        self.tabs.addTab(self.ms_pilot, 'MS Workflow')
        for index in range(self.tabs.count()):
            make_workspace_scrollable(self.tabs.widget(index))
        self.setCentralWidget(self.tabs)

    def closeEvent(self, event):
        self.projects.service.store.close()
        self.ledger.conn.close()
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = MSPilotWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
