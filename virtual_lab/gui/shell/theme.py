class Theme:
    # Backgrounds
    BG_0 = "#0d141d"  # App background
    BG_1 = "#16202d"  # Panel background
    BG_2 = "#1c2838"  # Card/input background

    # Borders
    BORDER = "#293647"
    
    # Text
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#8b9bb4"
    TEXT_MUTED = "#5c6d86"

    # Accents
    ACCENT = "#146de0"
    ACCENT_HOVER = "#2a7dec"
    
    # Status
    SUCCESS = "#22c55e"
    WARNING = "#eab308"
    ERROR = "#ef4444"

    # Epistemic states
    EPISTEMIC_MEASURED = "#22c55e"    # Green
    EPISTEMIC_CURATED = "#3b82f6"     # Blue
    EPISTEMIC_SIMULATED = "#06b6d4"   # Cyan
    EPISTEMIC_PREDICTED = "#f59e0b"   # Amber
    EPISTEMIC_HYPOTHETICAL = "#8b5cf6"# Violet
    EPISTEMIC_UNKNOWN = "#64748b"     # Gray

def get_stylesheet() -> str:
    return f"""
    QMainWindow, QWidget {{
        background-color: {Theme.BG_0};
        color: {Theme.TEXT_PRIMARY};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    
    QTabWidget::pane {{
        border: 1px solid {Theme.BORDER};
        background: {Theme.BG_0};
    }}
    
    QTabBar::tab {{
        background: {Theme.BG_1};
        color: {Theme.TEXT_SECONDARY};
        padding: 10px 18px;
        border: 1px solid {Theme.BORDER};
        border-bottom: none;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }}
    
    QTabBar::tab:selected {{
        background: {Theme.BG_0};
        color: {Theme.TEXT_PRIMARY};
        border-top: 2px solid {Theme.ACCENT};
    }}
    
    QTabBar::tab:hover:!selected {{
        background: {Theme.BG_2};
        color: {Theme.TEXT_PRIMARY};
    }}
    
    QGroupBox {{
        background-color: {Theme.BG_1};
        border: 1px solid {Theme.BORDER};
        border-radius: 6px;
        margin-top: 1.5ex;
        padding-top: 1ex;
    }}
    
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        color: {Theme.TEXT_SECONDARY};
        font-weight: bold;
    }}
    
    QPushButton {{
        background-color: {Theme.BG_2};
        border: 1px solid {Theme.BORDER};
        color: {Theme.TEXT_PRIMARY};
        padding: 6px 12px;
        border-radius: 4px;
    }}
    
    QPushButton:hover {{
        background-color: {Theme.BORDER};
    }}
    
    QPushButton#primary {{
        background-color: {Theme.ACCENT};
        border: none;
        font-weight: bold;
    }}
    
    QPushButton#primary:hover {{
        background-color: {Theme.ACCENT_HOVER};
    }}
    
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {Theme.BG_0};
        border: 1px solid {Theme.BORDER};
        padding: 4px 8px;
        border-radius: 4px;
        color: {Theme.TEXT_PRIMARY};
    }}
    
    QScrollBar:vertical {{
        background: {Theme.BG_0};
        width: 12px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {Theme.BORDER};
        min-height: 20px;
        border-radius: 6px;
        margin: 2px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    
    /* Dock widgets */
    QDockWidget {{
        titlebar-close-icon: url(close.png);
        titlebar-normal-icon: url(float.png);
        color: {Theme.TEXT_SECONDARY};
    }}
    
    QDockWidget::title {{
        background: {Theme.BG_1};
        padding: 6px;
        border-bottom: 1px solid {Theme.BORDER};
    }}
    """
