"""Prepare a visibly marked full-app directory draft; never submit or publish."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'integrations/chatgpt-directory'
FILES = ('plugin.json', 'mcp.json', 'assets/virtuallab.svg')


def inspect_package(directory=PACKAGE):
    directory = Path(directory)
    manifest = json.loads((directory/'plugin.json').read_text())
    profile = json.loads((directory/'release-profile.json').read_text())
    parity = json.loads((directory/'capability-parity.json').read_text())
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',manifest['name']) or len(manifest['name'])>64:
        raise ValueError('Invalid plugin identifier')
    ext = manifest['extensions']['com.openai']
    if any(key in ext for key in ('apps','hooks')) or (directory/'.app.json').exists():
        raise ValueError('Public draft must not contain local app references or lifecycle hooks')
    fields = ext['interface']
    for key, maximum in [('displayName',30),('shortDescription',30),('longDescription',4000),('developerName',80)]:
        if not isinstance(fields[key],str) or not fields[key].strip() or len(fields[key])>maximum:
            raise ValueError('Invalid listing field: '+key)
    for key in ('websiteURL','supportURL','privacyPolicyURL','termsOfServiceURL'):
        parsed=urlsplit(fields[key])
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('HTTPS publisher URL required: '+key)
    for key in ('logo','composerIcon'):
        value=fields[key]
        if not value.startswith('./') or '..' in Path(value).parts:
            raise ValueError('Asset must stay inside the package')
        image=directory/value[2:]
        if image.is_symlink() or not image.is_file() or image.stat().st_size>5*1024*1024:
            raise ValueError('Missing or oversized icon')
        svg=ET.parse(image).getroot()
        width,height=float(svg.attrib['width']),float(svg.attrib['height'])
        if width!=height or width<48:
            raise ValueError('Icon must be square and at least 48 pixels')
    review=ext['review']['test_cases']
    if len(review['positive'])<5 or len(review['negative'])<3:
        raise ValueError('Five positive and three negative review designs required')
    from virtual_lab.domain.research_domains import TOOLS
    expected={t.id for t in TOOLS.values() if t.status.value!='unavailable'}|{'settings'}
    if {c['id'] for c in parity['workspaces']}!=expected:
        raise ValueError('Full application workspace inventory is incomplete')
    blockers=[key for key,passed in profile['release_gates'].items() if passed is not True]
    blockers += ['workspace_parity:'+c['id'] for c in parity['workspaces']
                 if c['full_plugin_status']!='VERIFIED_IN_CHATGPT']
    # Even complete local preparation cannot establish portal review or publication.
    return {'format':'virtuallab-plugin-preparation','scope':profile['product_scope'],
        'support_email':profile['support_email'], 'local_documented_field_checks':'passed',
        'openai_validation_run':False,'ready_for_submission':not blockers,
        'submitted':False,'published':False,'searchable':False,'blocking_gates':blockers,
        'workspace_count':len(parity['workspaces']),
        'notice':'Local field checks are not official OpenAI validation or full application acceptance.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'output/plugin-directory-preparation')
    parser.add_argument('--require-ready',action='store_true')
    args=parser.parse_args(argv)
    report=inspect_package()
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'readiness.json').write_text(json.dumps(report,indent=2)+'\n')
    if args.require_ready and not report['ready_for_submission']:
        parser.error('Full application and publication gates remain open; read readiness.json. No release ZIP was produced.')
    destination=args.output/'VirtualLab-Full-Application-DRAFT.zip'
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(PACKAGE/name,name)
    (args.output/(destination.name+'.sha256')).write_text(
        hashlib.sha256(destination.read_bytes()).hexdigest()+'  '+destination.name+'\n')
    print(json.dumps({'draft_zip':str(destination),'ready_for_submission':report['ready_for_submission'],
                      'scope':report['scope'],'workspace_count':report['workspace_count'],
                      'blocking_gates':len(report['blocking_gates'])},indent=2))


if __name__=='__main__': main()
