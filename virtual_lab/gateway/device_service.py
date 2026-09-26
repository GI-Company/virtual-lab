"""
virtual_lab.gateway.device_service
──────────────────────────────────
Authoritative device management service.
Orchestrates device providers, validates device IDs, and enforces the Zero-Fabrication Rule.
"""

import re
from typing import Dict, Any, List, Optional
from virtual_lab.gateway.providers.base import DeviceProvider
from virtual_lab.gateway.providers.sensornode import SensorNodeProvider


class DeviceServiceError(Exception):
    pass


class InvalidDeviceIdError(DeviceServiceError):
    pass


class DeviceNotFoundError(DeviceServiceError):
    pass


class DeviceService:
    # Strict allowlist for device IDs: alphanumeric, hyphen, underscore, dot, colon (1-128 chars)
    DEVICE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.:]{1,128}$")

    def __init__(self, providers: Optional[List[DeviceProvider]] = None):
        self.providers: List[DeviceProvider] = providers if providers is not None else [SensorNodeProvider()]

    def register_provider(self, provider: DeviceProvider):
        """Add a hardware device provider."""
        self.providers.append(provider)

    def validate_device_id(self, device_id: str):
        """
        Validates device_id against strict allowlist.
        Rejects empty strings, path traversals, shell characters, and invalid lengths.
        """
        if not isinstance(device_id, str):
            raise InvalidDeviceIdError("Device ID must be a string.")
        
        device_id = device_id.strip()
        if not device_id:
            raise InvalidDeviceIdError("Device ID cannot be empty.")
            
        if ".." in device_id or "/" in device_id or "\\" in device_id:
            raise InvalidDeviceIdError("Device ID contains forbidden path traversal sequences.")

        if not self.DEVICE_ID_REGEX.match(device_id):
            raise InvalidDeviceIdError(f"Invalid device ID format: '{device_id}'. Allowed characters are [a-zA-Z0-9_-.:].")

    def list_devices(self) -> List[Dict[str, Any]]:
        """
        Aggregates all discovered devices across active providers.
        Returns empty list [] if no hardware is detected. Never fabricates devices.
        """
        all_devices = []
        seen_ids = set()

        for provider in self.providers:
            try:
                devs = provider.list_devices()
                for d in devs:
                    did = d.get("device_id")
                    if did and did not in seen_ids:
                        seen_ids.add(did)
                        all_devices.append(d)
            except Exception as e:
                # Log provider failure, but do not fabricate replacements
                continue

        return all_devices

    def describe_device(self, device_id: str) -> Dict[str, Any]:
        """
        Returns factual hardware characteristics for the specified device.
        Raises DeviceNotFoundError if device does not exist.
        """
        self.validate_device_id(device_id)

        for provider in self.providers:
            desc = provider.describe_device(device_id)
            if desc is not None:
                return desc

        raise DeviceNotFoundError(f"Device '{device_id}' was not found in Virtual Lab.")

    def get_status(self, device_id: str) -> Dict[str, Any]:
        """
        Returns real-time status and diagnostics for the specified device.
        Raises DeviceNotFoundError if device does not exist.
        """
        self.validate_device_id(device_id)

        for provider in self.providers:
            st = provider.get_status(device_id)
            if st is not None:
                return st

        raise DeviceNotFoundError(f"Device '{device_id}' was not found in Virtual Lab.")

    def get_calibration(self, device_id: str) -> Dict[str, Any]:
        """
        Returns factual calibration metadata for the specified device.
        Raises DeviceNotFoundError if device does not exist.
        """
        self.validate_device_id(device_id)

        for provider in self.providers:
            cal = provider.get_calibration(device_id)
            if cal is not None:
                return cal

        raise DeviceNotFoundError(f"Device '{device_id}' was not found in Virtual Lab.")
