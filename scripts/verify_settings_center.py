"""Native/offscreen Settings Center smoke check; no SDK, credentials or network."""
import argparse
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    os.environ['VIRTUALLAB_DATA_DIR']=str(output/'workspace')
    class NoSDK(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname.startswith(('google.genai','google.adk','mlx_lm','mlx.core')):
                raise ImportError('Verification forbids SDK/model loading')
    sys.meta_path.insert(0,NoSDK())
    def no_network(*args,**kwargs): raise AssertionError('Unexpected network attempt')
    socket.socket.connect=no_network
    socket.socket.bind=no_network
    import keyring
    keyring.get_password=no_network; keyring.set_password=no_network; keyring.delete_password=no_network
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from virtual_lab.gui.shell.main_window import VirtualLabApplication
    app=QApplication.instance() or QApplication([])
    window=VirtualLabApplication(); window.resize(1400,950); window.show()
    QTest.qWait(500)
    nav=window.navigation
    nav.show_library('mass_spectrometry')
    nav.new_name.setText('Settings verification — synthetic workflow')
    nav.create_project()
    project=nav.project_id
    exp=window.projects.service.create_experiment(project,'Preserved experiment','Settings verification only')
    before=window.ledger.conn.execute('SELECT COUNT(*) FROM ledger_events').fetchone()[0]
    nav.show_settings(); center=nav.settings
    assert window.ledger.conn.execute('SELECT COUNT(*) FROM ledger_events').fetchone()[0]==before
    assert window.runtime.agent_runtime is None and not window.settings_service.busy
    for index in range(center.tabs.count()):
        center.tabs.setCurrentIndex(index); QTest.qWait(150)
        assert window.grab().save(str(output/f'{index+1:02d}-settings.png'))
    center.fields['predictions_enabled'].setChecked(True)
    center.fields['learning_enabled'].setChecked(False)
    center.fields['assistant_enabled'].setChecked(False)
    center.fields['allow_cloud'].setChecked(False)
    center.fields['max_tokens'].setValue(512)
    center.save()
    center.scope.setCurrentIndex(center.scope.findData('project'))
    center.rule_fields['cloud'].setChecked(False)
    center.save()
    settings_hash=hashlib.sha256(window.settings_service.repository.path.read_bytes()).hexdigest()
    assert window.workspace.active_experiment.id==exp
    assert window.runtime.agent_runtime is None
    assert not window.runtime.gateway.server.isListening()
    window.close(); QTest.qWait(200)
    reopened=VirtualLabApplication(); reopened.show(); QTest.qWait(250)
    settings=reopened.settings_service.repository.load()
    assert settings.predictions_enabled and not settings.learning_enabled and not settings.assistant_enabled
    assert settings.max_tokens==512 and not settings.allow_cloud
    assert reopened.workspace.active_experiment.id==exp
    assert hashlib.sha256(reopened.settings_service.repository.path.read_bytes()).hexdigest()==settings_hash
    assert not reopened.settings_service.busy
    assert reopened.runtime.agent_runtime is None
    assert not reopened.runtime.gateway.server.isListening()
    reopened.navigation.show_settings()
    reopened.navigation.settings.tabs.setCurrentIndex(2)
    assert reopened.grab().save(str(output/'07-restarted.png'))
    reopened.close(); QTest.qWait(200)
    (output/'result.json').write_text(json.dumps({'status':'passed','platform':app.platformName(),
        'pages':6,'settings_sha256':settings_hash,'restart_preserved_experiment':True,
        'assistant':'off','learning':'off','listener':'off','sdk_imports':'blocked',
        'python_network':'blocked','scope':'Local UI/settings verification only'},indent=2))
    print('Settings Center native verification passed',flush=True)

if __name__=='__main__': main()
