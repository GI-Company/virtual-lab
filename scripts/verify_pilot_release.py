"""Reject mismatched builds, unsafe source archives and inconsistent wheel records."""
import argparse
import base64
import csv
import hashlib
import io
from pathlib import Path, PurePosixPath
import tarfile
import zipfile

MAX_ARCHIVE_BYTES=100*1024*1024


def safe_path(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or str(path)!=name.rstrip('/'):
        raise ValueError('Unsafe archive path: '+name)
    if any(part.startswith('.venv') or part in {'.git','__pycache__','.env'} for part in path.parts):
        raise ValueError('Private or generated data in release: '+name)
    return path


def verify_source(path):
    with tarfile.open(path,'r:gz') as archive:
        members=archive.getmembers()
        names=[m.name for m in members]
        if len(set(names))!=len(names): raise ValueError('Duplicate source archive entries')
        if len(names)>10000 or sum(m.size for m in members)>MAX_ARCHIVE_BYTES: raise ValueError('Source archive exceeds limits')
        for member in members:
            parts=safe_path(member.name).parts
            if len(parts)>1 and parts[1] in {'output','tmp','data'}:
                raise ValueError('Local data included in source archive')
            if not (member.isfile() or member.isdir()): raise ValueError('Linked or special source archive member')


def verify_wheel(wheel):
    with zipfile.ZipFile(wheel) as archive:
        inventory=archive.namelist()
        names=set(inventory)
        if len(names)!=len(inventory): raise ValueError('Duplicate wheel entries')
        if len(names)>10000 or sum(i.file_size for i in archive.infolist())>MAX_ARCHIVE_BYTES:
            raise ValueError('Wheel exceeds limits')
        for name in inventory: safe_path(name)
        required={'virtual_lab/pilots/desktop.py','virtual_lab/pilots/ms_workflow.py',
            'virtual_lab/pilots/reporting.py','virtual_lab/gui/ms_pilot_workspace.py'}
        if not required<=names: raise ValueError('Pilot files are missing from wheel')
        records=[n for n in names if n.endswith('.dist-info/RECORD')]
        if len(records)!=1: raise ValueError('Expected exactly one wheel RECORD')
        record=records[0]
        rows=list(csv.reader(io.StringIO(archive.read(record).decode())))
        if any(len(row)!=3 for row in rows): raise ValueError('Malformed wheel RECORD')
        if len({r[0] for r in rows})!=len(rows): raise ValueError('Duplicate wheel RECORD rows')
        if {r[0] for r in rows}!=names: raise ValueError('Wheel inventory does not match RECORD')
        for name,digest,size in rows:
            if name==record:
                if digest or size: raise ValueError('RECORD must leave its own digest and size blank')
                continue
            raw=archive.read(name)
            expected='sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
            if digest!=expected or len(raw)!=int(size): raise ValueError('Wheel RECORD mismatch: '+name)


def verify(first,second):
    first,second=Path(first),Path(second)
    files=sorted(p.name for p in first.iterdir() if p.name.endswith(('.whl','.tar.gz')))
    other=sorted(p.name for p in second.iterdir() if p.name.endswith(('.whl','.tar.gz')))
    if files!=other or len(files)!=2 or sum(n.endswith('.whl') for n in files)!=1:
        raise ValueError('Expected matching inventories with one wheel and one source archive')
    for name in files:
        if (first/name).read_bytes()!=(second/name).read_bytes(): raise ValueError('Build is not reproducible: '+name)
    verify_wheel(next(first.glob('*.whl')))
    verify_source(next(first.glob('*.tar.gz')))
    print('Reproducible wheel/source; safe inventories and all wheel RECORD entries verified')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first',type=Path)
    parser.add_argument('second',type=Path)
    args=parser.parse_args()
    verify(args.first,args.second)
