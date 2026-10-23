import pytest

from scripts.verify_acceptance import create_acceptance_bundles
from virtual_lab.core.provenance_export import explain_provenance


@pytest.fixture
def bundles(tmp_path_factory, trusted_publisher):
    return create_acceptance_bundles(tmp_path_factory.mktemp("bundle-acceptance"))


@pytest.mark.parametrize("name,expected", [
    ("pristine", "Genesis hash chain: VERIFIED"),
    ("missing_artifact", "Error:"),
    ("artifact_byte_changed", "Artifact hash mismatch"),
    ("genesis_event_changed", "Genesis hash mismatch"),
])
def test_signed_bundle_acceptance(bundles, name, expected):
    report = explain_provenance(str(bundles[name]))
    assert expected in report
    if name == "pristine":
        assert "Error:" not in report
        assert "[WARNING]" not in report
