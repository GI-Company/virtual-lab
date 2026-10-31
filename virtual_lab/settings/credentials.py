"""Settings credentials require an OS credential backend; no plaintext fallback."""
import keyring
from virtual_lab.core.credentials import APP_NAME

class OSCredentials:
    def _backend(self):
        backend = keyring.get_keyring()
        module = type(backend).__module__
        if not module.startswith(('keyring.backends.macOS', 'keyring.backends.Windows',
                                  'keyring.backends.SecretService', 'keyring.backends.kwallet')):
            raise RuntimeError('An OS credential store is unavailable; plaintext credential storage is disabled')
        return backend

    def get_api_key(self, provider_id):
        try:
            return self._backend().get_password(APP_NAME, provider_id)
        except Exception:
            return None

    def set_api_key(self, provider_id, api_key):
        backend = self._backend()
        try:
            backend.set_password(APP_NAME, provider_id, api_key)
        except Exception:
            raise RuntimeError('OS credential store could not save the credential') from None

    def remove_api_key(self, provider_id):
        from keyring.errors import PasswordDeleteError
        try:
            self._backend().delete_password(APP_NAME, provider_id)
        except PasswordDeleteError:
            pass
