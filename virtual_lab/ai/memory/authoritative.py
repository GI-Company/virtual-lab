from .types import AuthoritativeResolutionState
from .models import AuthoritativeReference

class AuthoritativeResolver:
    """
    Abstract/Facade boundary for resolving whether authoritative entities 
    actually exist in their respective origin stores.
    """
    def __init__(self):
        # In a real setup, this connects to ExperimentStore, EvidenceStore, etc.
        # For our test scenario, we mock resolution.
        self._mock_stores = {}

    def register_mock_entity(
        self,
        store_kind: str,
        entity_type: str,
        entity_id: str,
        content_hash: str,
        version: str | None = None,
    ):
        key = f"{store_kind}::{entity_type}::{entity_id}"
        self._mock_stores[key] = {"content_hash": content_hash, "version": version}

    def remove_mock_entity(self, store_kind: str, entity_type: str, entity_id: str):
        key = f"{store_kind}::{entity_type}::{entity_id}"
        if key in self._mock_stores:
            del self._mock_stores[key]

    def resolve(self, ref: AuthoritativeReference) -> AuthoritativeResolutionState:
        # Mock logic for tests
        key = f"{ref.store_kind}::{ref.entity_type}::{ref.entity_id}"
        
        # Test for store availability
        if ref.store_kind == "UNAVAILABLE_STORE":
            return AuthoritativeResolutionState.STORE_UNAVAILABLE

        if key not in self._mock_stores:
            return AuthoritativeResolutionState.MISSING
            
        entry = self._mock_stores[key]
        if isinstance(entry, dict):
            current_hash = entry.get("content_hash")
            current_version = entry.get("version")
        else:
            current_hash = entry
            current_version = None

        if ref.content_hash and current_hash != ref.content_hash:
            return AuthoritativeResolutionState.HASH_MISMATCH
        if ref.entity_version and current_version is not None and current_version != ref.entity_version:
            return AuthoritativeResolutionState.STALE
            
        return AuthoritativeResolutionState.VALID
