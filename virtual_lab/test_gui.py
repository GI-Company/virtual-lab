import pytest
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from PySide6.QtWidgets import QApplication
from virtual_lab.gui.main_window import MainWindow
from virtual_lab.core.state import WorkspaceState

def test_main_window_constructs(qtbot):
    workspace = WorkspaceState()
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    assert window is not None
    assert window.windowTitle() == "VirtualLab Desktop — RHO P23H"
