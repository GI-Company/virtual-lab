"""Home -> discipline library -> project workstation, using the shared study core."""

import json
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QStackedWidget,
    QScrollArea,
    QFrame,
    QFormLayout,
    QSizePolicy,
)
from virtual_lab.domain.research_domains import (
    DOMAINS,
    TOOLS,
    PROFILES,
    Availability,
    domain_by_id,
    tool_availability,
)
from virtual_lab.gui.shell.layout import make_workspace_scrollable
from virtual_lab.gui.shell.navigation_cards import DisciplineCard, RecentProjectCard


class ResearchNavigation(QWidget):
    pageChanged = Signal(str)

    def __init__(
        self, workspace, study, tabs, tools, *, profile="research", can_switch=None
    ):
        super().__init__()
        from virtual_lab.gui.shell.gui_gc import ensure_gui_gc

        ensure_gui_gc()
        if profile not in PROFILES:
            raise ValueError("Choose research or academia presentation")
        self.workspace, self.study, self.tabs, self.tools = (
            workspace,
            study,
            tabs,
            tools,
        )
        self.profile = PROFILES[profile]
        self.can_switch = can_switch or (lambda: True)
        self.project_id = None
        self.domain_id = "general"
        self._routing = True
        self._key = "research_navigation_v1:" + profile
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        bar = QHBoxLayout()
        self.home_button = QPushButton("Home")
        self.library_button = QPushButton("Project library")
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(lambda: self.action(self.show_settings))
        self.home_button.clicked.connect(lambda: self.action(self.show_home))
        self.library_button.clicked.connect(
            lambda: self.action(lambda: self.show_library(self.domain_id))
        )
        self.breadcrumb = QLabel()
        self.breadcrumb.setTextFormat(Qt.PlainText)
        self.breadcrumb.setWordWrap(True)
        bar.addWidget(self.home_button)
        bar.addWidget(self.library_button)
        self.breadcrumb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        bar.addWidget(self.breadcrumb, 1)
        bar.addWidget(self.settings_button)
        layout.addLayout(bar)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.home = self._build_home()
        self.library = self._build_library()
        self.workstation = self._build_workstation()
        self.settings = self._build_settings()
        for page in (self.home, self.library, self.workstation, self.settings):
            self.stack.addWidget(page)
        make_workspace_scrollable(self.home)
        make_workspace_scrollable(self.library)
        make_workspace_scrollable(self.settings)
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        tabs.currentChanged.connect(self._tool_changed)
        workspace.activeExperimentChanged.connect(self._context_changed)
        workspace.activeProjectChanged.connect(self._context_changed)
        self._routing = False
        self.restore()

    def action(self, fn):
        try:
            self.status.clear()
            fn()
        except Exception as exc:
            self.status.setText(str(exc))

    def _heading(self, layout, title, description):
        label = QLabel(title)
        label.setStyleSheet("font-size:23px;font-weight:bold;")
        label.setWordWrap(True)
        layout.addWidget(label)
        label = QLabel(description)
        label.setWordWrap(True)
        layout.addWidget(label)

    def _build_home(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(12)
        self._heading(layout, self.profile.title, self.profile.introduction)
        grid = QGridLayout()
        self.domain_grid = grid
        self._domain_columns = 2
        self.domain_buttons = {}
        for index, domain in enumerate(DOMAINS.values()):
            primary = [
                tool
                for tool in domain.tools
                if tool not in ("projects", "intent", "provenance")
            ]
            available = domain.id == "general" or any(
                tool_availability(t, self.tools) != Availability.UNAVAILABLE
                for t in primary
            )
            states = [tool_availability(t, self.tools) for t in primary]
            state = (
                Availability.UNAVAILABLE
                if not available
                else (
                    Availability.ENABLED
                    if domain.id == "general" or Availability.ENABLED in states
                    else Availability.EXPERIMENTAL
                )
            )
            installed = sum(
                tool_availability(t, self.tools) != Availability.UNAVAILABLE
                for t in domain.tools
            )
            button = DisciplineCard(domain, state, installed, len(domain.tools))
            button.clicked.connect(
                lambda checked=False, d=domain.id: self.action(
                    lambda: self.show_library(d)
                )
            )
            grid.addWidget(button, index // 2, index % 2)
            self.domain_buttons[domain.id] = button
        layout.addLayout(grid)
        layout.addWidget(QLabel("Recent projects"))
        self.home_search = QLineEdit()
        self.home_search.setPlaceholderText("Search all local projects")
        self.home_search.setAccessibleName("Search recent projects")
        self.home_search.textChanged.connect(self.refresh_recent)
        layout.addWidget(self.home_search)
        self.recent = QListWidget()
        self.recent.setMinimumHeight(140)
        self.recent.setMaximumHeight(270)
        self.recent.setSpacing(5)
        self.recent.setAccessibleName("Recent project cards")
        self.recent.itemDoubleClicked.connect(
            lambda item: self.action(lambda: self.open_project(item.data(Qt.UserRole)))
        )
        layout.addWidget(self.recent)
        self.recent_empty = QLabel(
            "No projects yet. Choose a discipline above to create a project or import a study."
        )
        self.recent_empty.setWordWrap(True)
        layout.addWidget(self.recent_empty)
        button = QPushButton("Open selected project")
        self.open_recent_button = button
        self.recent.currentItemChanged.connect(self._recent_selection_changed)
        button.clicked.connect(
            lambda: self.action(
                lambda: self.open_project(
                    self.recent.currentItem().data(Qt.UserRole)
                    if self.recent.currentItem()
                    else None
                )
            )
        )
        layout.addWidget(button)
        layout.addStretch(1)
        return page

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 3 if self.width() >= 1180 else 2
        if hasattr(self, "domain_grid") and columns != self._domain_columns:
            self._domain_columns = columns
            for index, button in enumerate(self.domain_buttons.values()):
                self.domain_grid.removeWidget(button)
                self.domain_grid.addWidget(button, index // columns, index % columns)
            for index in range(3):
                self.domain_grid.setColumnStretch(index, 1 if index < columns else 0)

    def _build_library(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(12)
        self.library_title = QLabel()
        self.library_title.setStyleSheet("font-size:23px;font-weight:bold;")
        layout.addWidget(self.library_title)
        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText("Search projects in this discipline")
        self.library_search.setAccessibleName("Search discipline projects")
        self.library_search.textChanged.connect(self.refresh_library)
        layout.addWidget(self.library_search)
        self.project_list = QListWidget()
        self.project_list.setMinimumHeight(170)
        self.project_list.itemDoubleClicked.connect(
            lambda item: self.action(lambda: self.open_project(item.data(Qt.UserRole)))
        )
        self.project_list.setMaximumHeight(280)
        layout.addWidget(self.project_list)
        self.empty_panel = QFrame()
        self.empty_panel.setObjectName("libraryEmptyState")
        self.empty_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.empty_panel.setStyleSheet(
            "QFrame#libraryEmptyState {background:#162536;border:1px dashed #42617e;border-radius:10px;}"
        )
        empty_layout = QVBoxLayout(self.empty_panel)
        empty_layout.setContentsMargins(24, 20, 24, 20)
        self.empty_title = QLabel()
        self.empty_title.setStyleSheet(
            "font-size:19px;font-weight:bold;background:transparent;"
        )
        empty_layout.addWidget(self.empty_title)
        self.empty = QLabel()
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("background:transparent;")
        empty_layout.addWidget(self.empty)
        empty_actions = QHBoxLayout()
        create_empty = QPushButton("Create a project")
        create_empty.setObjectName("primary")
        create_empty.clicked.connect(lambda: self._focus_field(self.new_name))
        import_empty = QPushButton("Import a study")
        import_empty.clicked.connect(lambda: self._focus_field(self.study_path))
        self.clear_search = QPushButton("Clear search")
        self.clear_search.clicked.connect(self.library_search.clear)
        for button in (create_empty, import_empty, self.clear_search):
            empty_actions.addWidget(button)
        empty_layout.addLayout(empty_actions)
        layout.addWidget(self.empty_panel)
        row = QHBoxLayout()
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("New project name")
        self.new_name.setAccessibleName("New discipline project name")
        create = QPushButton("Create project")
        create.clicked.connect(lambda: self.action(self.create_project))
        open_button = QPushButton("Open project")
        self.open_project_button = open_button
        self.project_list.currentItemChanged.connect(self._project_selection_changed)
        open_button.clicked.connect(
            lambda: self.action(lambda: self.open_project(self.selected_project()))
        )
        row.addWidget(self.new_name, 1)
        row.addWidget(create)
        row.addWidget(open_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Move selected project to discipline"))
        self.move_domain = QComboBox()
        for domain in DOMAINS.values():
            self.move_domain.addItem(domain.title, domain.id)
        move = QPushButton("Move project")
        self.move_project_button = move
        move.clicked.connect(lambda: self.action(self.move_project))
        row.addWidget(self.move_domain)
        row.addWidget(move)
        layout.addLayout(row)
        from virtual_lab.gui.projects_workspace import StudyPathEdit

        self.study_path = StudyPathEdit()
        row = QHBoxLayout()
        row.addWidget(self.study_path, 1)
        import_button = QPushButton("Import study package")
        import_button.clicked.connect(lambda: self.action(self.import_project))
        row.addWidget(import_button)
        layout.addLayout(row)
        layout.addWidget(QLabel("Tool availability in this installation"))
        self.availability = QListWidget()
        self.availability.setMinimumHeight(120)
        self.availability.setMaximumHeight(180)
        self.availability.setWordWrap(True)
        layout.addWidget(self.availability)
        layout.addStretch(1)
        return page

    def _build_workstation(self):
        self.tools["projects"].set_available_tools(set(self.tools))
        self.tools["projects"].context_switch_allowed = lambda: self.can_switch()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("Experiment"))
        self.experiments = QComboBox()
        self.experiments.setMinimumWidth(160)
        self.experiments.setAccessibleName("Project workstation experiment")
        open_exp = QPushButton("Open experiment")
        open_exp.clicked.connect(lambda: self.action(self.open_experiment))
        notebook = QPushButton("New experiment / notebook")
        notebook.clicked.connect(lambda: self.action(self.open_notebook))
        row.addWidget(self.experiments, 1)
        row.addWidget(open_exp)
        row.addWidget(notebook)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Other tools in this project"))
        self.more_tools = QComboBox()
        for tool in TOOLS.values():
            status = tool_availability(tool.id, self.tools)
            self.more_tools.addItem(tool.title + " | " + status.value, tool.id)
            self.more_tools.model().item(self.more_tools.count() - 1).setEnabled(
                status != Availability.UNAVAILABLE
            )
        button = QPushButton("Open tool")
        button.clicked.connect(
            lambda: self.action(lambda: self.open_tool(self.more_tools.currentData()))
        )
        row.addWidget(self.more_tools, 1)
        row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(self.tabs, 1)
        return page

    def _build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self._heading(
            layout,
            "Settings",
            "Current workspace status. Unified preferences and provider configuration are planned for Milestone 4.",
        )
        form = QFormLayout()
        self.settings_values = {}
        for key, title in [
            ("profile", "Presentation"),
            ("location", "Local workspace"),
            ("assistant", "Assistant session"),
            ("predictions", "INTENT predictions"),
            ("learning", "INTENT learning"),
        ]:
            value = QLabel()
            value.setTextFormat(Qt.PlainText)
            value.setWordWrap(True)
            label = QLabel(title)
            label.setMinimumWidth(160)
            form.addRow(label, value)
            self.settings_values[key] = value
        layout.addLayout(form)
        note = QLabel(
            "Opening this page does not activate a provider, start training or connect an instrument. Existing controls remain in their workstation tools."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.settings_intent_button = QPushButton("Open existing INTENT controls")
        self.settings_intent_button.clicked.connect(
            lambda: self.action(lambda: self.open_tool("intent"))
        )
        layout.addWidget(self.settings_intent_button)
        back = QPushButton("Return to research")
        back.clicked.connect(lambda: self.action(self._return_from_settings))
        layout.addWidget(back)
        layout.addStretch()
        return page

    def show_settings(self):
        values = {
            "profile": self.profile.title,
            "location": str(Path(self.study.store._db_path).parent),
            "assistant": self.workspace.ai_state.title(),
            "predictions": "Unavailable",
            "learning": "Unavailable",
        }
        if "intent" in self.tools:
            policy = self.tools["intent"].controller.policy()
            values["predictions"] = "On" if policy.predictions_enabled else "Off"
            values["learning"] = "On" if policy.learning_enabled else "Off"
        for key, value in values.items():
            self.settings_values[key].setText(value)
        self.settings_intent_button.setEnabled(
            bool(self.project_id and "intent" in self.tools)
        )
        self.stack.setCurrentWidget(self.settings)
        self.breadcrumb.setText(self.profile.title + " / Settings")
        self._state("settings")
        self.pageChanged.emit("settings")

    def _return_from_settings(self):
        if self.workspace.active_project_id:
            self._enter_workstation()
        else:
            self.show_home()

    def _state(self, page):
        value = json.dumps(
            {
                "version": 1,
                "page": page,
                "domain_id": self.domain_id,
                "project_id": self.project_id,
            }
        )
        with self.study.store._conn:
            self.study.store._conn.execute(
                "INSERT OR REPLACE INTO workspace_settings VALUES (?,?)",
                (self._key, value),
            )

    def _guard(self):
        if not self.can_switch():
            raise ValueError(
                "Finish or cancel the active run/recording before leaving this project."
            )

    def show_home(self):
        self._guard()
        self._routing = True
        try:
            self.study.activate(None)
        finally:
            self._routing = False
        self.project_id = None
        self.stack.setCurrentWidget(self.home)
        self.library_button.setEnabled(False)
        self.breadcrumb.setText(self.profile.title + " / Home")
        self.refresh_recent()
        self._state("home")
        self.pageChanged.emit("home")

    def show_library(self, domain_id):
        domain = domain_by_id(domain_id)
        self._guard()
        self._routing = True
        try:
            self.study.activate(None)
        finally:
            self._routing = False
        self.project_id = None
        self.domain_id = domain.id
        self.library_search.clear()
        self.new_name.clear()
        self.stack.setCurrentWidget(self.library)
        self.library_button.setEnabled(True)
        self.breadcrumb.setText(
            self.profile.title + " / " + domain.title + " / Projects"
        )
        self.refresh_library()
        self._state("library")
        self.pageChanged.emit("library")

    def _focus_field(self, field):
        field.setFocus(Qt.OtherFocusReason)
        field.selectAll()
        scroll = getattr(self.library, "workspace_scroll", None)
        if scroll:
            scroll.ensureWidgetVisible(field, 12, 20)

    def _project_selection_changed(self, *_):
        selected = self.selected_project() is not None
        self.open_project_button.setEnabled(selected)
        if hasattr(self, "move_project_button"):
            self.move_project_button.setEnabled(selected)

    def _recent_selection_changed(self, *_):
        current = self.recent.currentItem()
        self.open_recent_button.setEnabled(current is not None)
        for index in range(self.recent.count()):
            item = self.recent.item(index)
            card = self.recent.itemWidget(item)
            if card is not None:
                card.set_selected(item is current)

    def refresh_recent(self, *_):
        selected = (
            self.recent.currentItem().data(Qt.UserRole)
            if self.recent.currentItem()
            else None
        )
        self.recent.clear()
        experiments = self.study.store.list_experiments()
        for project in self.study.projects(search=self.home_search.text(), recent=True)[
            :12
        ]:
            domain = DOMAINS.get(project["domain_id"], DOMAINS["general"])
            count = sum(e["project_id"] == project["id"] for e in experiments)
            context = self.study.project_context(project["id"])
            subtitle = f"{domain.title}  |  {count} experiment(s)  |  " + (
                "Previously opened" if context.get("last_opened_utc") else "New project"
            )
            item = QListWidgetItem(project["name"] + " | " + domain.title)
            item.setData(Qt.UserRole, project["id"])
            item.setSizeHint(QSize(280, 78))
            self.recent.addItem(item)
            self.recent.setItemWidget(
                item, RecentProjectCard(project["name"], subtitle)
            )
            if project["id"] == selected:
                self.recent.setCurrentItem(item)
        has_rows = self.recent.count() > 0
        self._recent_selection_changed()
        self.recent.setVisible(has_rows)
        self.open_recent_button.setVisible(has_rows)
        self.recent_empty.setVisible(not has_rows)
        self.recent_empty.setText(
            "No projects match this search. Try another name."
            if self.home_search.text().strip()
            else "No projects yet. Choose a discipline above to create a project or import a study."
        )

    def refresh_library(self, *_):
        domain = domain_by_id(self.domain_id)
        self.library_title.setText(domain.title + " / Project library")
        selected = self.selected_project()
        self.project_list.clear()
        for project in self.study.projects(
            self.domain_id, self.library_search.text(), recent=True
        ):
            item = QListWidgetItem(project["name"])
            item.setData(Qt.UserRole, project["id"])
            self.project_list.addItem(item)
            if project["id"] == selected:
                self.project_list.setCurrentItem(item)
        has_rows = self.project_list.count() > 0
        self.project_list.setVisible(has_rows)
        self.empty_panel.setVisible(not has_rows)
        searching = bool(self.library_search.text().strip())
        self.empty_title.setText(
            "No matching projects" if searching else "Your research starts here"
        )
        self.empty.setText(
            "Try another project name, or clear the search to see this discipline’s projects."
            if searching
            else "Create a project to organize experiments and evidence, or import an existing study."
        )
        self.clear_search.setVisible(searching)
        self._project_selection_changed()
        self.availability.clear()
        from PySide6.QtGui import QColor

        for tool_id in domain.tools:
            tool = TOOLS[tool_id]
            state = tool_availability(tool_id, self.tools)
            label = {
                Availability.ENABLED: "Available",
                Availability.EXPERIMENTAL: "Experimental",
                Availability.UNAVAILABLE: "Unavailable",
            }[state]
            item = QListWidgetItem(tool.title + "  •  " + label)
            item.setToolTip(tool.note)
            item.setForeground(
                QColor(
                    {
                        Availability.ENABLED: "#89d9b1",
                        Availability.EXPERIMENTAL: "#f3cd82",
                        Availability.UNAVAILABLE: "#a4b1c1",
                    }[state]
                )
            )
            self.availability.addItem(item)
        self.move_domain.setCurrentIndex(self.move_domain.findData(domain.id))

    def selected_project(self):
        item = self.project_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def create_project(self):
        self._guard()
        project = self.study.create_project(self.new_name.text(), self.domain_id)
        self.new_name.clear()
        self.open_project(project)

    def move_project(self):
        self._guard()
        self.study.set_project_domain(
            self.selected_project(), self.move_domain.currentData()
        )
        self.refresh_library()
        self.refresh_recent()

    def import_project(self):
        self._guard()
        source = Path(self.study_path.text().strip()).expanduser()
        if not source.is_absolute() or source.suffix != ".vlab-study":
            raise ValueError("Enter a full path ending in .vlab-study")
        self.study.import_study(source)
        self.study_path.clear()

    def open_project(self, project_id):
        self._guard()
        self._routing = True
        try:
            self.study.open_project(project_id)
        finally:
            self._routing = False
        self._enter_workstation()

    def _context_changed(self, *_):
        if self._routing:
            return
        if self.workspace.active_project_id:
            self._enter_workstation()
        else:
            self.project_id = None
            self.stack.setCurrentWidget(self.home)
            self.library_button.setEnabled(False)
            self.breadcrumb.setText(self.profile.title + " / Home")
            self.refresh_recent()
            self._state("home")
            self.pageChanged.emit("home")

    def _enter_workstation(self):
        project = next(
            (
                p
                for p in self.study.projects()
                if p["id"] == self.workspace.active_project_id
            ),
            None,
        )
        if project is None:
            return
        self.project_id = project["id"]
        self.domain_id = project["domain_id"]
        domain = domain_by_id(self.domain_id)
        self._routing = True
        try:
            self.tools["projects"].set_project_context(self.project_id)
            self.experiments.clear()
            for row in self.study.store.list_experiments():
                if row["project_id"] == self.project_id:
                    self.experiments.addItem(row["label"] or row["id"], row["id"])
            exp = self.workspace.active_experiment
            if exp:
                self.experiments.setCurrentIndex(self.experiments.findData(exp.id))
            self.tabs.blockSignals(True)
            for tool_id, page in self.tools.items():
                index = self.tabs.indexOf(page)
                self.tabs.setTabText(
                    index,
                    TOOLS[tool_id].title.replace("&", "&&")
                    + (
                        " (experimental)"
                        if TOOLS[tool_id].status == Availability.EXPERIMENTAL
                        else ""
                    ),
                )
                self.tabs.setTabVisible(index, tool_id in domain.tools)
            self.tabs.blockSignals(False)
            self.stack.setCurrentWidget(self.workstation)
            self.library_button.setEnabled(True)
            self.breadcrumb.setText(
                self.profile.title + " / " + domain.title + " / " + project["name"]
            )
            target = (
                self.study.project_context(self.project_id).get("last_tool_id")
                or domain.default_tool
            )
            self.open_tool(target if target in self.tools else "projects")
        finally:
            self._routing = False
        self._state("workstation")
        self.pageChanged.emit("workstation")

    def open_tool(self, tool_id):
        if not self.project_id:
            raise ValueError("Open a project first")
        if (
            tool_id not in self.tools
            or tool_availability(tool_id, self.tools) == Availability.UNAVAILABLE
        ):
            raise ValueError("Tool unavailable in this installation")
        page = self.tools[tool_id]
        index = self.tabs.indexOf(page)
        self.tabs.setTabVisible(index, True)
        self.tabs.setCurrentWidget(page)
        self.study.save_project_tool(self.project_id, tool_id)
        self.stack.setCurrentWidget(self.workstation)
        self._state("workstation")
        self.pageChanged.emit("workstation")
        if tool_id == "instruments":
            self.status.setText(
                "Instrument controls are available. Start the listener explicitly when ready; opening/restoring this view does not connect hardware."
            )

    def _tool_changed(self, index):
        if self._routing or not self.project_id:
            return
        for tool_id, page in self.tools.items():
            if page is self.tabs.widget(index):
                self.study.save_project_tool(self.project_id, tool_id)
                break

    def open_experiment(self):
        self._guard()
        experiment = self.experiments.currentData()
        row = self.study.store.get_experiment(experiment) if experiment else None
        if row is None or row["project_id"] != self.project_id:
            raise ValueError("Select an experiment in this project")
        self.study.activate(experiment)

    def open_notebook(self):
        self.open_tool("projects")
        self.tools["projects"].setup_toggle.setChecked(True)

    def restore(self):
        row = self.study.store._conn.execute(
            "SELECT value FROM workspace_settings WHERE key=?", (self._key,)
        ).fetchone()
        try:
            saved = json.loads(row[0]) if row and len(row[0]) < 4096 else {}
            if not isinstance(saved, dict) or saved.get("version", 1) != 1:
                raise ValueError("Invalid saved navigation")
            page = saved.get("page")
            if page == "library":
                self.show_library(saved["domain_id"])
            elif page == "home":
                self.show_home()
            elif page == "workstation":
                self.open_project(saved["project_id"])
            elif page == "settings":
                if saved.get("project_id"):
                    self.open_project(saved["project_id"])
                else:
                    self.show_home()
                self.show_settings()
            else:
                self._routing = True
                try:
                    self.study.restore()
                finally:
                    self._routing = False
                if self.workspace.active_project_id:
                    self._enter_workstation()
                else:
                    self.show_home()
        except (ValueError, KeyError, TypeError):
            self.show_home()
