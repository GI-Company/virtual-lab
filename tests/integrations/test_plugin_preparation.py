"""A full-application listing must not silently become a minimal or ready release."""
import json
from pathlib import Path
import shutil
import pytest
from scripts.prepare_plugin_submission import PACKAGE, inspect_package, main


def test_full_application_draft_is_truthful_and_complete():
    report=inspect_package()
    assert report['workspace_count']==16
    assert report['support_email']=='cory.tortorici@globalintentcompany.space'
    assert not report['ready_for_submission'] and not report['searchable']
    assert not report['submitted'] and not report['published'] and not report['openai_validation_run']
    manifest=json.loads((PACKAGE/'plugin.json').read_text())
    assert 'license' not in manifest  # Do not invent redistribution terms for this repository.
    assert 'full' in manifest['description'].lower()
    assert not (PACKAGE/'.app.json').exists()


def test_minimal_inventory_cannot_pass_full_application_preparation(tmp_path):
    package=tmp_path/'package'
    shutil.copytree(PACKAGE,package)
    parity=json.loads((package/'capability-parity.json').read_text())
    parity['workspaces']=[row for row in parity['workspaces'] if row['id']=='ms_workflow']
    (package/'capability-parity.json').write_text(json.dumps(parity))
    with pytest.raises(ValueError,match='incomplete'):
        inspect_package(package)


def test_release_guard_refuses_unfinished_full_application(tmp_path):
    with pytest.raises(SystemExit) as stopped:
        main(['--output',str(tmp_path),'--require-ready'])
    assert stopped.value.code==2
    assert not list(tmp_path.glob('*.zip'))
    report=json.loads((tmp_path/'readiness.json').read_text())
    assert 'full_feature_parity' in report['blocking_gates']
    assert 'public_https_mcp_verified' in report['blocking_gates']
