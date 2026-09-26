"""
virtual_lab.gateway.providers.base
──────────────────────────────────
Abstract base class for all physical device providers in Virtual Lab.
Enforces the Zero-Fabrication Rule: if hardware cannot be reached or does not exist,
providers must return factual empty/unavailable/error states rather than mock data.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class DeviceProvider(ABC):
    """
    Abstract interface for hardware device providers.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this provider."""
        pass

    @abstractmethod
    def list_devices(self) -> List[Dict[str, Any]]:
        """
        Return a list of devices actually known and accessible to this provider.
        Must return an empty list [] if no hardware is detected. Never fabricate devices.
        """
        pass

    @abstractmethod
    def describe_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Return factual hardware characteristics for the specified device.
        Returns None if the device is not handled or not found by this provider.
        Unknown fields must be omitted or None. Never infer missing characteristics.
        """
        pass

    @abstractmethod
    def get_status(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Return runtime status and diagnostics for the specified device.
        Status values: 'ONLINE', 'OFFLINE', 'DEGRADED', 'BUSY', 'UNKNOWN'.
        Do not report ONLINE unless actual runtime evidence supports it.
        Returns None if the device is not found by this provider.
        """
        pass

    @abstractmethod
    def get_calibration(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Return existing calibration metadata only.
        Returns None if the device is not found by this provider.
        If the device is found but has no calibration records, return:
        {'status': 'UNAVAILABLE', 'reason': 'NO_CALIBRATION_RECORD'}
        Never generate calibration values.
        """
        pass
