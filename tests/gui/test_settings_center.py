"""Editable settings must persist without activating providers or losing research."""
from unittest.mock import Mock
from types import SimpleNamespace
import pytest
from PySide6.QtWidgets import QPushButton
from virtual_lab.settings import SettingsRepository, SettingsService
from virtual_lab.gui.shell.settings_center import SettingsCenter
from virtual_lab.gui.shell.layout import make_workspace_scrollable
from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.settings.runtime import ManagedAssistantRuntime
from virtual_lab.gui.ai.local_research_workspace import LocalResearchWorkspace

@pytest.fixture
def center(qtbot,tmp_path):
    service=SettingsService(SettingsRepository(tmp_path))
    workspace=WorkspaceState()
    panel=SettingsCenter(service,workspace=workspace)
    qtbot.addWidget(panel)
    make_workspace_scrollable(panel)
    panel.resize(800,600); panel.show()
    return panel,service,workspace

def test_six_pages_persist_independently_without_activation(center):
    panel,service,workspace=center
    assert panel.tabs.count()==6 and not service.busy
    panel.fields['predictions_enabled'].setChecked(True)
    panel.fields['learning_enabled'].setChecked(False)
    panel.fields['assistant_enabled'].setChecked(False)
    panel.fields['allow_cloud'].setChecked(False)
    panel.fields['max_tokens'].setValue(256)
    panel.save()
    saved=SettingsRepository(service.repository.root).load()
    assert saved.predictions_enabled and not saved.assistant_enabled and not saved.learning_enabled
    assert saved.max_tokens==256 and not service.busy and service._process is None
    panel.reload()
    assert panel.fields['predictions_enabled'].isChecked()
    assert workspace.active_experiment is None
    for i in range(6):
        panel.tabs.setCurrentIndex(i)
        assert panel.tabs.currentWidget().workspace_scroll is not None

def test_scope_and_credentials_never_in_settings(center):
    panel,service,workspace=center
    service.credentials=Mock()
    panel.key.setText('fixture-secret')
    panel.store_key()
    assert not panel.key.text()
    service.credentials.set_api_key.assert_called_once_with(panel.credential_account(),'fixture-secret')
    workspace._active_project_id='project-a'
    panel.scope.setCurrentIndex(panel.scope.findData('project'))
    panel.rule_fields['exports'].setChecked(False)
    panel.save()
    assert 'fixture-secret' not in service.repository.path.read_text()
    with pytest.raises(PermissionError): service.repository.require('exports','project-a')
    service.repository.require('exports','project-b')

def test_busy_reconfiguration_is_rejected_and_draft_preserved(center):
    panel,service,workspace=center
    service.reserve('training')
    panel.fields['provider.model'].setText('draft')
    panel.action(panel.save)
    assert 'Cancel' in panel.status.text()
    assert service.repository.load().provider.model==''
    assert panel.fields['provider.model'].text()=='draft'
    service.release('training')

def test_managed_assistant_has_no_environment_configuration(qtbot,tmp_path,monkeypatch):
    service=SettingsService(SettingsRepository(tmp_path))
    s=service.repository.load().model_dump(); s['assistant_enabled']=True; service.save(s)
    monkeypatch.setenv('VIRTUALLAB_AI_PROVIDER','vertex')
    panel=LocalResearchWorkspace(WorkspaceState(),agent_runtime=ManagedAssistantRuntime(service))
    qtbot.addWidget(panel)
    assert panel.provider.isHidden() and panel.txt_vertex_key.isHidden()
    assert panel.btn_send.isEnabled()
    panel._apply_vertex_key()
    assert service.repository.load().provider.kind=='compatible'
    s['assistant_enabled']=False; service.save(s); panel._refresh_vertex_status()
    assert not panel.btn_send.isEnabled()


# Reuse the loopback-only fixture; no external providers are contacted.
from tests.settings.test_settings import server


def test_managed_assistant_round_trip_uses_saved_provider(qtbot,tmp_path,server):
    service=SettingsService(SettingsRepository(tmp_path))
    service.credentials=SimpleNamespace(get_api_key=lambda _:None)
    saved=service.repository.load().model_dump()
    saved['assistant_enabled']=True
    saved['provider'].update(model='fixture-model',endpoint=server[0])
    service.save(saved)
    workspace=WorkspaceState()
    panel=LocalResearchWorkspace(workspace,agent_runtime=ManagedAssistantRuntime(service))
    panel.controller=Mock()
    qtbot.addWidget(panel)
    panel.txt_prompt.setPlainText('hello')
    panel._on_send()
    qtbot.waitUntil(lambda:'fixture answer' in panel.lbl_answer.text(),timeout=10000)
    qtbot.waitUntil(lambda:panel.agent_thread is None or not panel.agent_thread.isRunning(),timeout=5000)
    assert panel.shutdown_agent_runtime()
    assert server[1][0]['model']=='fixture-model'
    assert 'UNVERIFIED' in panel.lbl_tags.text()
    assert not service.busy and service._process is None


def test_mcp_controls_default_off_and_preserve_project_categories(center):
    panel,service,workspace=center
    assert not panel.fields['mcp_enabled'].isChecked()
    assert all(not field.isEnabled() for field in panel.mcp_access.values())
    workspace._active_project_id='shared-project'
    panel.reload()
    panel.fields['mcp_enabled'].setChecked(True)
    panel.mcp_access['metadata'].setChecked(True)
    panel.mcp_access['reports'].setChecked(True)
    panel.mcp_access['spectrum'].setChecked(False)
    panel.save()
    saved=service.repository.load()
    assert saved.mcp_enabled and saved.mcp_projects['shared-project'].metadata
    assert saved.mcp_projects['shared-project'].reports and not saved.mcp_projects['shared-project'].spectrum
    assert not service.busy and service._process is None
    with pytest.raises(PermissionError): service.repository.require('mcp','shared-project',route='cloud')
    workspace._active_project_id='other-project'
    panel.reload()
    assert not any(field.isChecked() for field in panel.mcp_access.values())
    panel.fields['mcp_enabled'].setChecked(False)
    panel.save()
    assert service.repository.load().mcp_projects['shared-project'].reports
