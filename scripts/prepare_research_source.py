"""Package the reviewable working source with per-file SHA-256; never publish."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {'virtual_lab','tests','scripts','docs','integrations','protocol','examples','.github'}
ROOT_FILES = {'README.md','pyproject.toml','uv.lock','release_manifest.json','requirements-cockpit.txt',
              'start_virtuallab.sh','.gitignore','.gitattributes','LICENSE','LICENSE.md','LICENSE.txt'}


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)


def package(destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Choose a new archive path')
    files = git('ls-files','--cached','--others','--exclude-standard','-z').decode().split('\0')
    selected = {}
    for name in sorted(set(files)-{''}):
        relative = Path(name)
        if relative.parts[0] not in DIRECTORIES and name not in ROOT_FILES:
            continue
        if any(part in ('__pycache__','.venv','.git','.env','output','node_modules') for part in relative.parts):
            continue
        path = ROOT/relative
        if path.is_symlink():
            raise ValueError('Source package refuses symbolic links: '+name)
        if not path.is_file():
            continue
        if path.stat().st_size > 8*1024*1024:
            raise ValueError('Unexpected large source file: '+name)
        selected[name] = path.read_bytes()
    required = ['virtual_lab/application/engine.py','virtual_lab/integrations/research_service/server.py',
                'integrations/shared-engine-contract/command.schema.json',
                'integrations/shared-engine-contract/service-ms-report.schema.json']
    if not all(name in selected for name in required):
        raise ValueError('Review source is missing required engine/transport/contracts')
    notes = {'format':'virtuallab-source-review-v1','created_at':datetime.now(timezone.utc).isoformat(),
        'base_commit':git('rev-parse','HEAD').decode().strip(),
        'branch':git('branch','--show-current').decode().strip(),
        'includes_uncommitted_work':bool(git('status','--porcelain').strip()),
        'file_count':len(selected),'private_laboratory_data_included':False,
        'synthetic_test_fixtures_included':True,'published':False,'signed':False,
        'scope':'Working source snapshot, not a new released/certified application or deployed service.',
        'reproduce':'See docs/read-only-research-service.md. Verify SOURCE-MANIFEST.json before running.'}
    selected['SOURCE-REVIEW.json'] = (json.dumps(notes,indent=2,sort_keys=True)+'\n').encode()
    manifest = {'algorithm':'SHA-256','files':{name:hashlib.sha256(raw).hexdigest() for name,raw in selected.items()}}
    selected['SOURCE-MANIFEST.json'] = (json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    prefix = 'virtual-lab-review-source/'
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(selected.items()):
            entry = zipfile.ZipInfo(prefix+name,date_time=(1980,1,1,0,0,0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (0o100644 << 16)
            archive.writestr(entry,raw)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.zip.sha256').write_text(digest+'  '+destination.name+'\n')
    return {'archive':str(destination),'sha256':digest,'files':len(selected),'base_commit':notes['base_commit'],
            'includes_uncommitted_work':notes['includes_uncommitted_work']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.output)))


if __name__ == '__main__':
    main()
