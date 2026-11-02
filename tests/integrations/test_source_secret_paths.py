"""The same exact secret-review policy applies on Windows and POSIX hosts."""
import re

from scripts.verify_source_secrets import source_path, source_exclusion


def test_windows_paths_match_canonical_reviewed_names():
    assert source_path(r'docs\evidence\report.json', windows=True) == 'docs/evidence/report.json'
    assert source_path('docs/evidence/report.json', windows=True) == 'docs/evidence/report.json'
    # A literal backslash in a POSIX filename is not a directory separator.
    assert source_path(r'docs\evidence\report.json', windows=False) == r'docs\evidence\report.json'


def test_exclusions_have_identical_scope_on_each_platform():
    names = ['virtual_lab/gui/assets/molstar.js',
             'integrations/shared-engine-contract/source-secret-review.json',
             'virtual_lab/__pycache__/example.pyc']
    for name in names:
        assert re.search(source_exclusion(windows=False), name)
        assert re.search(source_exclusion(windows=True), name.replace('/', '\\'))
    for name in ['virtual_lab/gui/assets/other.js',
                 'integrations/shared-engine-contract/service-access-policy.schema.json',
                 'docs/evidence/report.json']:
        assert not re.search(source_exclusion(windows=False), name)
        assert not re.search(source_exclusion(windows=True), name.replace('/', '\\'))
    assert not re.search(source_exclusion(windows=False), r'virtual_lab\gui\assets\molstar.js')
