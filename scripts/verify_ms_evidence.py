"""Verify an unsigned synthetic demonstration packet, optionally without installing VirtualLab."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--hashes-only',action='store_true')
    args=parser.parse_args()
    root=args.directory.resolve()
    inventory=json.loads((root/'packet-manifest.json').read_bytes())
    if inventory.get('data_kind') not in ('synthetic_demonstration','public_reference_workflow_tests'): raise ValueError('Not a synthetic demo packet')
    for name,pin in inventory['files'].items():
        path=root/name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Unsafe packet path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=pin: raise ValueError('File digest mismatch: '+name)
    reports=inventory.get('reports',[{'pdf':'ms-workflow-report.pdf','json':'ms-workflow-report.json','receipt':'export-receipt.json','manifest':'evidence/manifest.json'}])
    for entry in reports:
        if not all(name in inventory['files'] for name in entry.values()): raise ValueError('Unlisted report reference')
        report=json.loads((root/entry['json']).read_bytes())
        receipt=json.loads((root/entry['receipt']).read_bytes())['payload']
        for key,digest_key in [('pdf','report_sha256'),('json','supporting_json_sha256')]:
            if hashlib.sha256((root/entry[key]).read_bytes()).hexdigest()!=receipt[digest_key]: raise ValueError('Export receipt mismatch')
        if not args.hashes_only:
            from virtual_lab.pilots.ms_workflow import verify_centroid_bundle
            result=verify_centroid_bundle(root/entry['manifest'],expected_manifest_sha256=report['manifest_sha256'])
            if result['peak_count']!=report['summary']['peak_count'] or result['run_id']!=report['manifest']['run_id']:
                raise ValueError('Report identity or peak count mismatch')
            print('Source normalization and artifact integrity verified: '+entry['manifest'])
    print('Packet and export-receipt hashes verified. This unsigned packet does not authenticate publisher or instrument origin.')


if __name__=='__main__': main()
