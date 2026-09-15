from PySide6.QtWidgets import QLabel, QWidget, QHBoxLayout
from PySide6.QtCore import Qt
from virtual_lab.gui.shell.theme import Theme

class StatusBadge(QLabel):
    def __init__(self, text: str, color: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color}20; /* 20 is alpha transparency in hex if supported, else we just use solid color */
                color: {color};
                border: 1px solid {color};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        self.setAlignment(Qt.AlignCenter)

class EpistemicBadge(StatusBadge):
    def __init__(self, state_str: str, parent=None):
        color_map = {
            "MEASURED": Theme.EPISTEMIC_MEASURED,
            "CURATED": Theme.EPISTEMIC_CURATED,
            "SIMULATED": Theme.EPISTEMIC_SIMULATED,
            "PREDICTED": Theme.EPISTEMIC_PREDICTED,
            "INCOMPLETE": Theme.EPISTEMIC_PREDICTED,
            "HYPOTHETICAL": Theme.EPISTEMIC_HYPOTHETICAL
        }
        color = color_map.get(state_str.upper(), Theme.EPISTEMIC_UNKNOWN)
        super().__init__(state_str.upper(), color, parent)
