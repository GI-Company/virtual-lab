import sys
from pathlib import Path

# Add project root to sys.path if needed
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from PySide6.QtWidgets import QApplication
from virtual_lab.core.state import WorkspaceState
from virtual_lab.gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    workspace = WorkspaceState()
    window = MainWindow(workspace)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
