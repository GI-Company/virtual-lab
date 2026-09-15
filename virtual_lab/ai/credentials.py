import keyring
from typing import Optional

APP_NAME = "virtuallab"

class CredentialService:
    """Service layer for secure credential management."""
    
    def __init__(self):
        # We can inject a fake keyring or mock for tests here in the future
        self._keyring = keyring

    def get_api_key(self, provider_id: str) -> Optional[str]:
        """Retrieve API key from macOS Keychain."""
        try:
            return self._keyring.get_password(APP_NAME, provider_id)
        except Exception:
            # If keychain is unavailable or errors out, we strictly disable the provider
            # by returning None, rather than falling back to plaintext or env vars.
            return None

    def set_api_key(self, provider_id: str, api_key: str):
        """Store API key in macOS Keychain."""
        self._keyring.set_password(APP_NAME, provider_id, api_key)
        
    def remove_api_key(self, provider_id: str):
        """Remove API key from macOS Keychain."""
        try:
            self._keyring.delete_password(APP_NAME, provider_id)
        except Exception:
            pass

# Legacy functions for compatibility
def get_api_key(provider_id: str) -> Optional[str]:
    return CredentialService().get_api_key(provider_id)

def set_api_key(provider_id: str, api_key: str):
    CredentialService().set_api_key(provider_id, api_key)
