import keyring
from typing import Optional

APP_NAME = "virtuallab"

def get_api_key(provider_id: str) -> Optional[str]:
    """Retrieve API key from macOS Keychain."""
    try:
        return keyring.get_password(APP_NAME, provider_id)
    except Exception:
        # If keychain is unavailable or errors out, we strictly disable the provider
        # by returning None, rather than falling back to plaintext or env vars.
        return None

def set_api_key(provider_id: str, api_key: str):
    """Store API key in macOS Keychain."""
    keyring.set_password(APP_NAME, provider_id, api_key)
