"""Headless test defaults and per-test application storage isolation."""

import os
import sys

import pytest

if sys.platform != "darwin":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_application_data(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("VIRTUALLAB_EDITION", "researcher")
    root = tmp_path_factory.mktemp("application-data")
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(root))
    if os.environ.get("VIRTUALLAB_RUN_LIVE_AI_TESTS") != "1":
        # Offline UI tests must never query or change the user's Keychain.
        import keyring

        credentials = {}
        monkeypatch.setattr(keyring, "get_password", lambda service, account: credentials.get((service, account)))
        monkeypatch.setattr(keyring, "set_password", lambda service, account, value: credentials.__setitem__((service, account), value))
        monkeypatch.setattr(keyring, "delete_password", lambda service, account: credentials.pop((service, account), None))


@pytest.fixture
def trusted_publisher(monkeypatch):
    """Explicit ephemeral test publisher; never trust the compromised demo key."""
    import nacl.signing
    from virtual_lab.core.trusted_signers import _REGISTRY, TrustedSigner, TrustState, SignerRole, _fingerprint
    key = nacl.signing.SigningKey.generate()
    public = key.verify_key.encode().hex()
    monkeypatch.setenv('VLAB_PUBLISHER_SK', key.encode().hex())
    monkeypatch.setitem(_REGISTRY, public, TrustedSigner('test-publisher', public,
        _fingerprint(public), TrustState.TRUSTED, [SignerRole.BUNDLE_PUBLISHER], 'test'))
    return key
