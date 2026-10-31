"""Central settings UI; opening it never initializes an SDK or starts a request."""
import json
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QCheckBox, QSpinBox, QPushButton, QComboBox, QTabWidget, QPlainTextEdit, QGridLayout)
from virtual_lab.settings import Settings, Restrictions, Provider
from virtual_lab.settings.service import credential_account

class ProviderTask(QThread):
    completed = Signal(str)
    def __init__(self, service, discover, parent):
        super().__init__(parent)
        self.service, self.discover = service, discover
    def run(self):
        try:
            value = self.service.request('Reply with OK.', discover=self.discover, test=True)
            # Connection tests only display bounded text, never SDK diagnostics or credentials.
            self.completed.emit('Available model IDs: '+json.dumps(value) if self.discover else 'Connection request succeeded; scientific capability is unvalidated.')
        except Exception as exc:
            self.completed.emit(str(exc))

class SettingsCenter(QWidget):
    def __init__(self, service, *, intent=None, workspace=None, parent=None):
        super().__init__(parent)
        self.service, self.intent, self.workspace = service, intent, workspace
        self.task = None
        self.fields = {}
        layout = QVBoxLayout(self)
        title = QLabel('Settings Center')
        title.setStyleSheet('font-size:23px;font-weight:bold;')
        layout.addWidget(title)
        note = QLabel('Save preferences explicitly. Enabling a switch grants permission; it does not start a model, training job or instrument connection. Provider calls use only the selected route, with no fallback.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        layout.addWidget(self.tabs)
        forms = {}
        for name in ('General', 'AI & Models', 'INTENT', 'Monitor', 'Privacy', 'Performance'):
            page = QWidget()
            form = QFormLayout(page)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            self.tabs.addTab(page, name)
            forms[name] = form
        def check(page, key, label):
            field = QCheckBox(label)
            forms[page].addRow(field)
            self.fields[key] = field
            return field
        def line(page, key, label):
            field = QLineEdit()
            forms[page].addRow(label, field)
            self.fields[key] = field
            return field
        def spin(page, key, label, lo, hi):
            field = QSpinBox(); field.setRange(lo, hi)
            forms[page].addRow(label, field)
            self.fields[key] = field
        self.location = QLabel(str(service.repository.root)); self.location.setWordWrap(True)
        forms['General'].addRow('Workspace', self.location)
        forms['General'].addRow(QLabel('Preferences are local to this workspace. Research data remain in their existing study storage.'))
        check('AI & Models', 'assistant_enabled', 'Permit conversational AI assistance')
        self.kind = QComboBox()
        for title, key in [('OpenAI-compatible server (text)', 'compatible'), ('Embedded MLX (experimental text)', 'mlx'), ('Gemini API (text)', 'gemini'), ('Vertex AI (text)', 'vertex')]:
            self.kind.addItem(title, key)
        forms['AI & Models'].addRow('Provider', self.kind)
        for key, label in [('model','Explicit model identifier'), ('endpoint','Compatible server base URL'), ('model_path','Existing MLX model folder'), ('project','Vertex project (ADC)'), ('location','Vertex location')]:
            line('AI & Models', 'provider.'+key, label)
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('New credential; saved only to the OS credential store')
        forms['AI & Models'].addRow('Credential', self.key)
        row = QGridLayout()
        for index, (label, fn) in enumerate([('Store credential', self.store_key), ('Remove credential', self.remove_key), ('Test connection', lambda:self.start_test(False)), ('Discover server models', lambda:self.start_test(True))]):
            b = QPushButton(label); b.clicked.connect(lambda checked=False, f=fn:self.action(f)); row.addWidget(b,index//2,index%2)
        forms['AI & Models'].addRow(row)
        check('INTENT', 'predictions_enabled', 'Permit INTENT predictions')
        check('INTENT', 'learning_enabled', 'Permit INTENT learning')
        forms['INTENT'].addRow(QLabel('Project training permission, signed measured outcomes, frozen holdout and manual promotion remain required in the INTENT workspace.'))
        self.monitor = QPlainTextEdit(); self.monitor.setReadOnly(True); self.monitor.setMinimumHeight(160)
        forms['Monitor'].addRow(self.monitor)
        row = QHBoxLayout()
        for label, fn in [('Refresh status', self.refresh_monitor), ('Cancel / unload model', self.cancel)]:
            b=QPushButton(label); b.clicked.connect(lambda checked=False,f=fn:self.action(f)); row.addWidget(b)
        forms['Monitor'].addRow(row)
        for key, label in [('allow_loopback','Permit loopback servers'), ('allow_lan','Permit LAN server routes'), ('allow_cloud','Permit cloud routes'), ('allow_tools','Permit AI tool execution (text adapters expose no tools)'), ('allow_exports','Permit governed research exports')]:
            check('Privacy',key,label)
        check('Privacy', 'mcp_enabled', 'MCP Access: permit sharing through a separately launched integration')
        self.mcp_access = {}
        for key, label in [('metadata', 'Share metadata for the active project'),
                           ('reports', 'Share summary reports for the active project'),
                           ('spectrum', 'Share spectrum points for the active project')]:
            field = QCheckBox(label)
            self.mcp_access[key] = field
            forms['Privacy'].addRow(field)
        mcp_note = QLabel('MCP is off by default. Sharing also requires cloud-route and export permission. Spectrum points require separate consent. Saving does not launch a server or connect ChatGPT. The prototype serves frozen public/synthetic MS snapshots only.')
        mcp_note.setWordWrap(True)
        forms['Privacy'].addRow(mcp_note)
        self.scope = QComboBox()
        for label, value in [('Application defaults','application'), ('Current project restrictions','project'), ('Current experiment restrictions','experiment')]:
            self.scope.addItem(label,value)
        forms['Privacy'].addRow('Restrict scope',self.scope)
        self.rule_fields={}
        rule_row=QGridLayout()
        for index,key in enumerate(Restrictions.model_fields):
            field=QCheckBox(key); self.rule_fields[key]=field; rule_row.addWidget(field,index//3,index%3)
        forms['Privacy'].addRow('Allowed within scope',rule_row)
        self.scope.currentIndexChanged.connect(self.refresh_scope)
        admin = QLabel('Restrictions intersect: administrator → application → project → experiment. A lower scope cannot grant a permission denied above it. Administrator policy is supplied through VIRTUALLAB_ADMIN_POLICY and protected by local OS access.')
        admin.setWordWrap(True); forms['Privacy'].addRow(admin)
        line('Performance','model_directory','Model registry folder (absolute path)')
        spin('Performance','min_free_gib','Minimum free disk (GiB)',1,10000)
        spin('Performance','max_model_gib','Maximum model files (GiB)',1,1024)
        spin('Performance','timeout_seconds','Provider timeout (seconds)',5,600)
        spin('Performance','max_tokens','Maximum output tokens',1,8192)
        forms['Performance'].addRow(QLabel('No automatic model downloads. Inference and INTENT training share one job slot. Each provider process exits after a request to release model memory. File size is checked; it is not a RAM guarantee.'))
        row=QHBoxLayout()
        for label, fn in [('Save settings',self.save),('Reload saved settings',self.reload)]:
            b=QPushButton(label); b.clicked.connect(lambda checked=False,f=fn:self.action(f)); row.addWidget(b)
        layout.addLayout(row)
        self.status=QLabel(); self.status.setWordWrap(True); self.status.setTextFormat(Qt.PlainText); layout.addWidget(self.status)
        self.reload()

    def action(self, fn):
        try:
            fn()
        except Exception as exc:
            self.status.setText(str(exc))

    def scope_id(self):
        if not self.workspace:
            return None
        if self.scope.currentData()=='project':
            return self.workspace.active_project_id
        exp=self.workspace.active_experiment
        return exp.id if exp else None

    def refresh_scope(self, *_):
        s=self.service.repository.load()
        scope=self.scope.currentData()
        rules=s.project_rules if scope=='project' else s.experiment_rules
        rule=rules.get(self.scope_id(),Restrictions())
        for key, field in self.rule_fields.items():
            field.setChecked(getattr(rule,key)); field.setEnabled(scope!='application' and bool(self.scope_id()))

    def reload(self):
        s=self.service.repository.load()
        self.kind.setCurrentIndex(self.kind.findData(s.provider.kind))
        for key, field in self.fields.items():
            value=getattr(s.provider,key.split('.')[1]) if key.startswith('provider.') else getattr(s,key)
            if isinstance(field,QCheckBox): field.setChecked(value)
            elif isinstance(field,QSpinBox): field.setValue(value)
            else: field.setText(value)
        self.key.clear()
        project = self.workspace.active_project_id if self.workspace else None
        access = s.mcp_projects.get(project)
        for key, field in self.mcp_access.items():
            field.setChecked(bool(access and getattr(access, key)))
            field.setEnabled(bool(project))
        self.refresh_scope(); self.refresh_monitor()
        self.status.setText('Saved preferences loaded. No provider activated.')

    def save(self):
        data=self.service.repository.load().model_dump()
        data['provider']['kind']=self.kind.currentData()
        for key, field in self.fields.items():
            value=field.isChecked() if isinstance(field,QCheckBox) else field.value() if isinstance(field,QSpinBox) else field.text().strip()
            if key.startswith('provider.'): data['provider'][key.split('.')[1]]=value
            else: data[key]=value
        project = self.workspace.active_project_id if self.workspace else None
        if project:
            data['mcp_projects'][project] = {key:field.isChecked() for key,field in self.mcp_access.items()}
        scope=self.scope.currentData()
        if scope!='application':
            identity=self.scope_id()
            if not identity: raise ValueError('Open a project / experiment before saving scoped restrictions')
            data['project_rules' if scope=='project' else 'experiment_rules'][identity]={k:f.isChecked() for k,f in self.rule_fields.items()}
        value=Settings.model_validate(data)
        self.service.save(value)
        if self.intent is not None:
            policy=self.intent.controller.policy().model_dump()
            policy.update(predictions_enabled=value.predictions_enabled,learning_enabled=value.learning_enabled)
            self.intent.controller.set_policy(policy)
            # Preserve any draft inputs in the INTENT workspace.
            self.intent.predictions.setChecked(value.predictions_enabled)
            self.intent.learning.setChecked(value.learning_enabled)
        self.status.setText('Settings saved. No request or training job started.')
        self.refresh_monitor()

    def credential_account(self):
        data = self.service.repository.load().provider.model_dump()
        data['kind'] = self.kind.currentData()
        data['endpoint'] = self.fields['provider.endpoint'].text().strip()
        return credential_account(Provider.model_validate(data))

    def store_key(self):
        if self.service.busy: raise RuntimeError('Cancel active work before changing credentials')
        value=self.key.text().strip()
        if not value: raise ValueError('Enter a credential')
        self.service.credentials.set_api_key(self.credential_account(),value)
        self.key.clear(); self.status.setText('Credential stored in OS credential store.')

    def remove_key(self):
        if self.service.busy: raise RuntimeError('Cancel active work before changing credentials')
        self.service.credentials.remove_api_key(self.credential_account())
        self.key.clear(); self.status.setText('Credential removal requested.')

    def start_test(self, discover):
        if self.task is not None and self.task.isRunning(): raise RuntimeError('A connection test is already running')
        self.save()
        self.task=ProviderTask(self.service,discover,self)
        self.task.completed.connect(self.status.setText)
        self.task.finished.connect(self.refresh_monitor)
        self.task.start()
        self.status.setText('Testing the saved provider; no research data sent.')

    def cancel(self):
        self.service.unload()
        if self.intent is not None and self.intent.busy: self.intent.cancel()
        self.status.setText('Cancellation requested. Wait for worker exit before changing models.')
        self.refresh_monitor()

    def refresh_monitor(self):
        info=self.service.resource_status()
        info['registry']=self.service.registry()
        info['capabilities']=self.service.capabilities()
        if self.intent is not None:
            info['intent_training_active']=self.intent.busy
            project=self.workspace.active_project_id if self.workspace else None
            info['intent_models']=[dict(model_id=m['model_id'],
                active_checkpoint=self.intent.controller.active(m['model_id']),
                candidate_checkpoint=self.intent.controller.candidate(m['model_id']))
                for m in self.intent.controller.models(project)]
        self.monitor.setPlainText(json.dumps(info,indent=2,default=str))
