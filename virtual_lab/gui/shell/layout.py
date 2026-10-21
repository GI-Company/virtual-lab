"""Keep workspace controls usable when the desktop window is smaller than a page."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea, QAbstractSpinBox, QComboBox, QFormLayout, QFrame,
    QGraphicsView, QLabel, QLayout, QLineEdit, QListWidget, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget,
    QTableWidget, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)


def _prepare_controls(root):
    for label in root.findChildren(QLabel):
        if label.pixmap() is not None and not label.pixmap().isNull():
            continue
        label.setWordWrap(True)
        policy = label.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Preferred)
        label.setSizePolicy(policy)
    for form in root.findChildren(QFormLayout):
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for widget in root.findChildren(QWidget):
        if isinstance(widget, QLineEdit) and isinstance(widget.parentWidget(), (QAbstractSpinBox, QComboBox)):
            continue  # The owning input sizes its private editor inside its frame.
        if isinstance(widget, (QLineEdit, QComboBox, QAbstractSpinBox, QPushButton)):
            widget.setMinimumHeight(max(widget.minimumHeight(), min(30, widget.maximumHeight())))
        elif isinstance(widget, (QPlainTextEdit, QTextEdit)):
            widget.setMinimumHeight(max(widget.minimumHeight(), min(96, widget.maximumHeight())))
        elif isinstance(widget, (QListWidget, QTableWidget)):
            widget.setMinimumHeight(max(widget.minimumHeight(), min(120, widget.maximumHeight())))
            widget.setMinimumWidth(max(widget.minimumWidth(), 260 if isinstance(widget, QTableWidget) else 160))
        elif isinstance(widget, QGraphicsView) or widget.inherits('QWebEngineView'):
            widget.setMinimumSize(max(260, widget.minimumWidth()), max(220, widget.minimumHeight()))
        if isinstance(widget, QSplitter):
            widget.setChildrenCollapsible(False)
        if isinstance(widget, QScrollArea) and widget.widget() is not None:
            content_layout = widget.widget().layout()
            if content_layout is not None:
                content_layout.setSizeConstraint(QLayout.SetMinimumSize)
        if isinstance(widget, QTabWidget):
            widget.setUsesScrollButtons(True)
            widget.setElideMode(Qt.ElideNone)


def make_workspace_scrollable(workspace):
    """Preserve page identity/signals while giving its layout a scroll viewport.

    Nested tab/stack pages scroll independently, including hidden pages. Existing
    scroll areas are reused. Layout minimum sizes drive the scroll ranges, so
    expanding forms or switching models updates overflow without fixed page sizes.
    """
    if hasattr(workspace, 'workspace_scroll'):
        return workspace.workspace_scroll
    _prepare_controls(workspace)
    for tabs in workspace.findChildren(QTabWidget):
        for index in range(tabs.count()):
            make_workspace_scrollable(tabs.widget(index))
    for stack in workspace.findChildren(QStackedWidget):
        if isinstance(stack.parentWidget(), QTabWidget):
            continue
        for index in range(stack.count()):
            make_workspace_scrollable(stack.widget(index))
    if isinstance(workspace, QTabWidget):
        for index in range(workspace.count()):
            make_workspace_scrollable(workspace.widget(index))
        workspace.setUsesScrollButtons(True)
        workspace.setElideMode(Qt.ElideNone)
        return None
    if isinstance(workspace, QAbstractScrollArea):
        return workspace
    old_layout = workspace.layout()
    if old_layout is None:
        return None
    # Projects already has a full-page scroll area; don't nest another around it.
    if old_layout.count() == 1 and isinstance(old_layout.itemAt(0).widget(), QScrollArea):
        scroll = old_layout.itemAt(0).widget()
        workspace.workspace_scroll = scroll
        return scroll
    content = QWidget()
    content.setLayout(old_layout)
    old_layout.setSizeConstraint(QLayout.SetMinimumSize)
    scroll = QScrollArea(workspace)
    scroll.setObjectName('workspaceScroll')
    scroll.setAccessibleName('Scrollable workspace')
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setFocusPolicy(Qt.StrongFocus)
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    layout = QVBoxLayout(workspace)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(scroll)
    workspace.workspace_scroll = scroll
    return scroll
