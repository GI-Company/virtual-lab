"""Headless test defaults and per-test application storage isolation."""

import os
import sys

import pytest

if sys.platform != "darwin":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_application_data(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("application-data")
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(root))
    if os.environ.get("VIRTUALLAB_RUN_LIVE_AI_TESTS") != "1":
        # Offline UI tests must never query or change the user's Keychain.
        import keyring

        credentials = {}
        monkeypatch.setattr(keyring, "get_password", lambda service, account: credentials.get((service, account)))
        monkeypatch.setattr(keyring, "set_password", lambda service, account, value: credentials.__setitem__((service, account), value))
        monkeypatch.setattr(keyring, "delete_password", lambda service, account: credentials.pop((service, account), None))
