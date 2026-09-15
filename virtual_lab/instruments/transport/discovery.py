import socket
import os
import logging
from enum import Enum
from typing import List, Optional
from zeroconf import Zeroconf, ServiceInfo, NonUniqueNameException
from virtual_lab.version import __version__

logger = logging.getLogger(__name__)

class DiscoveryStatus(Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    ADVERTISING = "ADVERTISING"
    FAILED = "FAILED"

class InstrumentDiscoveryService:
    def __init__(self, port: int = 8765):
        self.port = port
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self._status = DiscoveryStatus.STOPPED
        self._advertised_addresses: List[str] = []
        self._registered_name = "VirtualLab Desktop"
        self._base_name = "VirtualLab Desktop"

    def status(self) -> DiscoveryStatus:
        return self._status

    def advertised_addresses(self) -> List[str]:
        return self._advertised_addresses
        
    def registered_name(self) -> str:
        return self._registered_name

    def _resolve_ip(self) -> Optional[str]:
        # 1. Environment variable override
        env_ip = os.environ.get("VIRTUALLAB_DISCOVERY_ADDRESS")
        if env_ip:
            return env_ip

        # 2. Try to get a valid LAN IP
        try:
            # UDP connect trick (doesn't send data)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # 8.8.8.8 is used to force the OS to pick the interface that routes to the internet
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                
                # Check if it's a link-local or loopback
                if not (ip.startswith("127.") or ip.startswith("169.254.")):
                    return ip
        except Exception:
            pass
            
        # 3. Fallback: gethostbyname
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if not (ip.startswith("127.") or ip.startswith("169.254.")):
                return ip
        except Exception:
            pass
            
        return None

    def start(self):
        if self._status == DiscoveryStatus.ADVERTISING:
            return # Idempotent

        self._status = DiscoveryStatus.STARTING
        
        ip_addr = self._resolve_ip()
        if not ip_addr:
            self._status = DiscoveryStatus.FAILED
            logger.error("Discovery Failed: No usable LAN address found.")
            return

        self._advertised_addresses = [ip_addr]
        
        properties = {
            b"protocol_version": b"1",
            b"path": b"/sensors",
            b"app": b"VirtualLab",
            b"version": __version__.encode("utf-8"),
        }
        
        try:
            self.zeroconf = Zeroconf()
            
            # Attempt registration, handling name collisions
            counter = 0
            while True:
                name = self._base_name if counter == 0 else f"{self._base_name} ({counter})"
                type_ = "_virtuallab._tcp.local."
                
                self.service_info = ServiceInfo(
                    type_,
                    f"{name}.{type_}",
                    addresses=[socket.inet_aton(ip_addr)],
                    port=self.port,
                    properties=properties,
                    server=f"{name.replace(' ', '')}.local."
                )
                
                try:
                    self.zeroconf.register_service(self.service_info)
                    self._registered_name = name
                    self._status = DiscoveryStatus.ADVERTISING
                    break
                except NonUniqueNameException:
                    counter += 1
                    if counter > 10:
                        raise RuntimeError("Too many VirtualLab instances on the network")
                        
        except Exception as e:
            logger.error(f"Failed to start mDNS: {e}")
            if self.zeroconf:
                self.zeroconf.close()
                self.zeroconf = None
            self._status = DiscoveryStatus.FAILED

    def stop(self):
        if self._status == DiscoveryStatus.STOPPED:
            return # Idempotent
            
        if self.zeroconf:
            if self.service_info:
                try:
                    self.zeroconf.unregister_service(self.service_info)
                except Exception:
                    pass
            self.zeroconf.close()
            
        self.zeroconf = None
        self.service_info = None
        self._advertised_addresses = []
        self._status = DiscoveryStatus.STOPPED
