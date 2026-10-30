"""Compare reproducible builds and verify wheel RECORD hashes and pilot contents."""
import argparse
import base64
import csv
import hashlib
import io
from pathlib import Path
import zipfile


def verify(first, second):
    files = sorted(p.name for p in first.iterdir() if p.suffix in ('.whl', '.gz'))
    if not any(n.endswith('.whl') for n in files) or not any(n.endswith('.tar.gz') for n in files):
        raise ValueError('Expected a wheel and source archive')
    for name in files:
        if (first/name).read_bytes() != (second/name).read_bytes():
            raise ValueError('Build is not reproducible: ' + name)
    wheel = next(first.glob('*.whl'))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        required = {'virtual_lab/pilots/desktop.py', 'virtual_lab/pilots/ms_workflow.py',
            'virtual_lab/pilots/reporting.py', 'virtual_lab/gui/ms_pilot_workspace.py'}
        if not required <= names:
            raise ValueError('Pilot files are missing from wheel')
        record = next(n for n in names if n.endswith('.dist-info/RECORD'))
        rows = list(csv.reader(io.StringIO(archive.read(record).decode())))
        if {r[0] for r in rows} != names:
            raise ValueError('Wheel inventory does not match RECORD')
        for name, digest, size in rows:
            if name == record:
                continue
            raw = archive.read(name)
            expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
            if digest != expected or len(raw) != int(size):
                raise ValueError('Wheel RECORD mismatch: ' + name)
    print('Reproducible wheel and source archive; all wheel RECORD entries verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    args = parser.parse_args()
    verify(args.first, args.second)
