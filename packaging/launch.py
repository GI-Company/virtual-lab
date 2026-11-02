"""Thin launcher for PyInstaller packaging of VirtualLab desktop cockpit."""

import sys
from virtual_lab.gui.shell.main_window import VirtualLabApplication
from PySide6.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VirtualLab")
    app.setOrganizationName("Global Intent Company")
    app.setOrganizationDomain("globalintentcompany.space")
    window = VirtualLabApplication()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
