"""Exercise real workspace geometry in a separate browser/Qt process."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QAbstractSpinBox, QComboBox, QGraphicsView,
    QFormLayout, QLineEdit, QPushButton, QScrollArea, QStackedWidget, QTabWidget, QWidget)

from manual_research_flow import close_window
from virtual_lab.gui.shell.main_window import VirtualLabApplication
from virtual_lab.gui.shell.layout import make_workspace_scrollable
from virtual_lab.gui.ai.local_research_workspace import LocalResearchWorkspace
from virtual_lab.gui.services.simulation_runner import RunConfig, run_simulation
from virtual_lab.gui.services.simulation_result import SimulationResult


def main(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    os.environ['VIRTUALLAB_DATA_DIR'] = str(root/'data')
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = VirtualLabApplication()
    # Layout inspection must not activate a network listener or AI runtime.
    window.tabs.blockSignals(True)
    window.projects.service.create_project('Research project with a long but ordinary descriptive name')
    project_id = window.projects.service.projects()[0]['id']
    window.projects.service.create_experiment(project_id, 'An experiment with a descriptive name',
        'Can all research controls and saved results be reached in a small application window?')
    window._refresh_context()
    window.projects.setup_toggle.setChecked(True)
    window.biological.maturation_enabled.setChecked(True)
    window.calibration.mode.setCurrentIndex(1)
    window.experiment.model_selector.setCurrentIndex(window.experiment.model_selector.findData('gene_expression'))
    result = SimulationResult.from_dict(run_simulation(RunConfig(model_id='gene_expression', members=4, duration_h=1)))
    window.workspace.current_result = result
    window.analysis.list_endpoints.setCurrentRow(1)
    optional_panel = LocalResearchWorkspace(window.workspace, agent_runtime=MagicMock())
    make_workspace_scrollable(optional_panel)
    optional_panel.lbl_answer.setText('An extended saved research response with explicit assumptions and limitations. '*20)
    optional_panel.approval_panel.show()
    optional_panel.lbl_pending.setText('Review this pending proposal and its stated assumptions before making a decision. '*3)
    window.ai_layout.addWidget(optional_panel)
    window.show()
    report = []

    def inspect_page(name, page):
        app.processEvents()
        scrolls = page.findChildren(QScrollArea)
        if isinstance(page, QScrollArea):
            scrolls = [page, *scrolls]
        for scroll in scrolls:
            if not scroll.isVisible() or scroll.widget() is None:
                continue
            content = scroll.widget()
            # Overflow must have a usable range, not just a cropped viewport.
            assert scroll.horizontalScrollBar().maximum() >= content.width()-scroll.viewport().width()-1, name
            assert scroll.verticalScrollBar().maximum() >= content.height()-scroll.viewport().height()-1, name
        for form in page.findChildren(QFormLayout):
            for row in range(form.rowCount()):
                label = form.itemAt(row, QFormLayout.LabelRole)
                if label is not None and label.widget() is not None and label.widget().isVisible():
                    assert label.widget().width() > 12, (name, 'collapsed field label')
        for widget in page.findChildren(QWidget):
            if not isinstance(widget, (QLineEdit, QComboBox, QAbstractSpinBox, QPushButton, QGraphicsView)) or not widget.isVisible():
                continue
            assert widget.height() >= widget.minimumHeight(), (name, widget.objectName(), widget.height())
            parent = widget.parentWidget()
            bounds = widget.geometry()
            # Standard layout children must stay inside their immediate panel.
            # Scroll contents may exceed their viewport, and are checked above.
            assert bounds.left() >= -1 and bounds.top() >= -1, (name, type(widget).__name__, bounds)
            assert bounds.right() <= parent.width()+1, (name, type(widget).__name__, bounds, parent.size())
            assert bounds.bottom() <= parent.height()+1, (name, type(widget).__name__, bounds, parent.size())
        report.append({'page':name, 'window':[window.width(), window.height()],
            'scroll_ranges':[[s.horizontalScrollBar().maximum(), s.verticalScrollBar().maximum()]
                for s in page.findChildren(QScrollArea) if s.isVisible()]})

    for width, height in [(800,600), (1200,800), (1600,1000)]:
        window.resize(width, height)
        QTest.qWait(60)
        for index in range(window.tabs.count()):
            window.tabs.setCurrentIndex(index)
            page = window.tabs.widget(index)
            name = window.tabs.tabText(index)
            QTest.qWait(20)
            # The selected page itself must fit the tab viewport.
            origin = page.mapTo(window, QPoint())
            assert origin.x() >= 0 and origin.y() >= 0, name
            assert origin.x()+page.width() <= window.width(), name
            assert origin.y()+page.height() <= window.height(), name
            inspect_page(name, page)
            for tabs in page.findChildren(QTabWidget):
                for subindex in range(tabs.count()):
                    tabs.setCurrentIndex(subindex)
                    inspect_page(name+'/'+tabs.tabText(subindex), tabs.widget(subindex))
            for stack in page.findChildren(QStackedWidget):
                if isinstance(stack.parentWidget(), QTabWidget):
                    continue
                for subindex in range(stack.count()):
                    stack.setCurrentIndex(subindex)
                    inspect_page(name+'/stack-'+str(subindex), stack.widget(subindex))
            if '--screenshots' in sys.argv:
                for scroll in page.findChildren(QScrollArea):
                    scroll.verticalScrollBar().setValue(0)
                    scroll.horizontalScrollBar().setValue(0)
                app.processEvents()
                window.grab().save(str(root/f'{width}-{index:02}-top.png'))
                for scroll in page.findChildren(QScrollArea):
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                    scroll.horizontalScrollBar().setValue(scroll.horizontalScrollBar().maximum())
                app.processEvents()
                window.grab().save(str(root/f'{width}-{index:02}-bottom.png'))
    # Dock the real optional panel with long content at every supported size.
    # No provider is created and no cloud request is made.
    window.local_research = optional_panel
    for width, height in [(800, 600), (1200, 800), (1600, 1000)]:
        window._place_ai_in_tab()
        window.ai_dock.hide()
        window.resize(width, height)
        window._toggle_ai_drawer(True)
        QTest.qWait(60)
        assert window.width() <= width and window.height() <= height, ('dock expanded window', window.size())
        assert window.ai_dock.geometry().right() < window.width()
        assert window.project_label.width() > 150
        assert window.experiment_label.width() > 150
        assert window.pipeline_hint.height() >= window.pipeline_hint.heightForWidth(window.pipeline_hint.width())
        inspect_page('Docked assistant', window.ai_dock_scroll)
        scroll = window.pipeline_scroll
        assert scroll.horizontalScrollBar().maximum() >= scroll.widget().width()-scroll.viewport().width()-1
        scroll.horizontalScrollBar().setValue(scroll.horizontalScrollBar().maximum())
        assert window.btn_ai_drawer.mapTo(scroll.viewport(), QPoint()).x() < scroll.viewport().width()
        if '--screenshots' in sys.argv:
            window.grab().save(str(root/f'{width}-assistant-dock.png'))
        window._toggle_ai_drawer(False)
        assert window.ai_layout.indexOf(optional_panel) >= 0
    assert not window.runtime.gateway.server.isListening()
    assert window.runtime.agent_runtime is None
    assert optional_panel.shutdown_agent_runtime()
    (root/'layout-report.json').write_text(json.dumps(report, indent=2))
    close_window(app, window)
    print(f'layout passed: {len(report)} populated page/size combinations')


if __name__ == '__main__':
    main(sys.argv[1])
