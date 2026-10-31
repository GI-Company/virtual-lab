"""Offline source secret gate. Print finding locations, never candidate values."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT/'integrations/shared-engine-contract/source-secret-review.json'
PATHS = ['virtual_lab','tests','scripts','docs','integrations','.github','README.md','pyproject.toml','.gitignore']


def main():
    policy = json.loads(POLICY.read_bytes())
    assert set(policy) == {'format','scanner','reviewed_nonsecrets','pinned_vendor_assets'}
    assert policy['format'] == 'virtuallab-source-secret-review-v1'
    reasons = {
        'Reviewed checksum, protocol example digest or public verification key; not a signing secret.',
        'Reviewed fixed dummy credential, rejected input or fake environment value in an offline test; not a real credential.',
        'Reviewed public source commit identifier in qualification metadata; not a credential.',
    }
    for entry in policy['reviewed_nonsecrets']:
        assert set(entry) == {'file','type','hashed_secret','reason'}
        assert (ROOT/entry['file']).resolve().is_relative_to(ROOT)
        assert re.fullmatch('[a-f0-9]{40}',entry['hashed_secret']) and entry['reason'] in reasons
    assert set(policy['pinned_vendor_assets']) == {'virtual_lab/gui/assets/molstar.js'}
    for name, asset in policy['pinned_vendor_assets'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != asset['sha256']:
            raise SystemExit('Vendored asset changed; repeat secret review: '+name)
    # The large, already reviewed vendor bundle is pinned above, not silently
    # ignored when its bytes change. Generated binary caches are not source.
    # The review file contains only finding digests and constrained descriptions;
    # scanning those digests recursively would create an endless baseline.
    exclude = r'(__pycache__/|\.pyc$|\.db$|^virtual_lab/gui/assets/molstar\.js$|^integrations/shared-engine-contract/source-secret-review\.json$)'
    process = subprocess.run([sys.executable,'-m','detect_secrets','scan','--no-verify','--all-files',
        '--exclude-files',exclude,*PATHS],cwd=ROOT,capture_output=True,text=True,check=True)
    results = json.loads(process.stdout)['results']
    allowed = {(e['file'],e['type'],e['hashed_secret']) for e in policy['reviewed_nonsecrets']}
    unexpected = []
    count = 0
    for filename, findings in results.items():
        for finding in findings:
            count += 1
            if (filename,finding['type'],finding['hashed_secret']) not in allowed:
                unexpected.append({'file':filename,'line':finding['line_number'],'type':finding['type']})
    print(json.dumps({'passed':not unexpected,'scanner':'detect-secrets 1.5.0',
        'verification':'offline; no candidate sent to credential providers',
        'reviewed_nonsecret_matches':count-len(unexpected),'unexpected_findings':unexpected}))
    if unexpected:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
