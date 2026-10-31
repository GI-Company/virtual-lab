"""Presentation refinements must preserve scope, accessibility and safe defaults."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
from virtual_lab.pilots.desktop import MSPilotWindow


def test_empty_state_and_search_have_actionable_routes(qtbot):
    window = MSPilotWindow()
    qtbot.addWidget(window)
    window.show()
    nav = window.navigation
    nav.show_library("mass_spectrometry")
    assert nav.empty_panel.isVisible() and not nav.project_list.isVisible()
    create = next(
        b
        for b in nav.empty_panel.findChildren(QPushButton)
        if b.text() == "Create a project"
    )
    create.click()
    assert window.focusWidget() is nav.new_name
    nav.new_name.setText("A useful project")
    nav.create_project()
    nav.show_library("mass_spectrometry")
    assert nav.project_list.isVisible() and not nav.empty_panel.isVisible()
    nav.library_search.setText("no-such-project")
    assert nav.empty_panel.isVisible() and nav.clear_search.isVisible()
    nav.clear_search.click()
    assert nav.project_list.count() == 1
    nav.show_home()
    assert nav.recent.count() == 1
    card = nav.recent.itemWidget(nav.recent.item(0))
    assert (
        card.name_label.text() == "A useful project"
        and "Mass Spectrometry" in card.subtitle_label.text()
    )
    window.close()


def test_settings_overview_is_read_only_and_restores_context(qtbot):
    window = MSPilotWindow()
    qtbot.addWidget(window)
    window.show()
    nav = window.navigation
    nav.show_library("mass_spectrometry")
    nav.new_name.setText("Settings scope")
    nav.create_project()
    project = nav.project_id
    exp = window.projects.service.create_experiment(project, "Planned", "Software test")
    before = window.intent_panel.controller.policy().model_dump()
    count = window.ledger.conn.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[
        0
    ]
    nav.settings_button.click()
    assert nav.stack.currentWidget() is nav.settings
    assert window.workspace.active_experiment.id == exp
    assert (
        nav.settings_values["predictions"].text() == "Off"
        and nav.settings_values["learning"].text() == "Off"
    )
    assert before == window.intent_panel.controller.policy().model_dump()
    assert (
        window.ledger.conn.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0]
        == count
    )
    nav.settings_intent_button.click()
    assert (
        nav.stack.currentWidget() is nav.workstation
        and window.tabs.currentWidget() is window.intent_panel
    )
    nav.show_settings()
    window.close()
    reopened = MSPilotWindow()
    qtbot.addWidget(reopened)
    assert reopened.navigation.stack.currentWidget() is reopened.navigation.settings
    assert reopened.workspace.active_experiment.id == exp
    assert (
        not reopened.intent_panel.learning.isChecked()
        and reopened.workspace.ai_state == "off"
    )
    reopened.close()


def test_tiles_remain_accessible_and_project_labels_are_plain_text(qtbot):
    window = MSPilotWindow()
    qtbot.addWidget(window)
    nav = window.navigation
    for domain, card in nav.domain_buttons.items():
        assert card.accessibleName() and card.title_label.textFormat() == Qt.PlainText
        assert card.status_label.text() in ("Available", "Experimental", "Unavailable")
        assert card.isEnabled() == (card.status_label.text() != "Unavailable")
    nav.show_library("mass_spectrometry")
    nav.new_name.setText("<b>Literal project</b>")
    nav.create_project()
    nav.show_home()
    card = nav.recent.itemWidget(nav.recent.item(0))
    assert (
        card.name_label.text() == "<b>Literal project</b>"
        and card.name_label.textFormat() == Qt.PlainText
    )
    project = nav.recent.item(0).data(Qt.UserRole)
    nav.open_project(project)
    nav.can_switch = lambda: False
    with pytest.raises(ValueError, match="Finish or cancel"):
        window.projects._return_to_staging()
    assert window.workspace.active_project_id is not None
    nav.can_switch = lambda: True
    window.close()
