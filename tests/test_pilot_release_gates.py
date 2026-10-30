import base64
import csv
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile
import pytest
from scripts.verify_pilot_release import verify_wheel, verify_source


def make_wheel(path, *, corrupt=False, duplicate=False):
    files={name:b'# pilot\n' for name in ('virtual_lab/pilots/desktop.py','virtual_lab/pilots/ms_workflow.py',
        'virtual_lab/pilots/reporting.py','virtual_lab/gui/ms_pilot_workspace.py')}
    record='virtual_lab-1.dist-info/RECORD'
    stream=io.StringIO(); writer=csv.writer(stream)
    for name,raw in files.items():
        digest='sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
        writer.writerow([name,digest,len(raw)])
    writer.writerow([record,'',''])
    with zipfile.ZipFile(path,'w') as archive:
        for name,raw in files.items(): archive.writestr(name,b'changed' if corrupt and name.endswith('desktop.py') else raw)
        archive.writestr(record,stream.getvalue())
        if duplicate:
            with pytest.warns(UserWarning): archive.writestr(record,stream.getvalue())


def test_wheel_record_tampering_and_duplicate_entries_rejected(tmp_path):
    good=tmp_path/'good.whl';make_wheel(good);verify_wheel(good)
    bad=tmp_path/'bad.whl';make_wheel(bad,corrupt=True)
    with pytest.raises(ValueError,match='RECORD mismatch'): verify_wheel(bad)
    duplicate=tmp_path/'duplicate.whl';make_wheel(duplicate,duplicate=True)
    with pytest.raises(ValueError,match='Duplicate wheel'): verify_wheel(duplicate)


@pytest.mark.parametrize('name,link', [('package/.venv/bin/python',False),('package/output/lab.csv',False),('package/../secret',False),('package/link',True)])
def test_source_archive_rejects_private_paths_and_links(tmp_path,name,link):
    target=tmp_path/'bad.tar.gz'
    with tarfile.open(target,'w:gz') as archive:
        info=tarfile.TarInfo(name)
        if link: info.type=tarfile.SYMTYPE; info.linkname='/private/secret'
        else: info.size=1
        archive.addfile(info,None if link else io.BytesIO(b'x'))
    with pytest.raises(ValueError): verify_source(target)


@pytest.mark.parametrize('case',['<failure message="failed"/>','<error message="error"/>','<skipped message="not run"/>'])
def test_failed_or_all_skipped_suite_cannot_generate_release_manifest(tmp_path,case):
    junit=tmp_path/'results.xml'
    junit.write_text('<testsuite><testcase name="case">'+case+'</testcase></testsuite>')
    output=tmp_path/'manifest.json'
    script=Path(__file__).resolve().parents[1]/'scripts/generate_release_manifest.py'
    result=subprocess.run([sys.executable,str(script),'--junit',str(junit),'--wheel',str(tmp_path/'missing.whl'),
        '--output',str(output)],capture_output=True,text=True,timeout=15)
    assert result.returncode!=0
    assert 'Refusing release manifest' in result.stderr
    assert not output.exists()
