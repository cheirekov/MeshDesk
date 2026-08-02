from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from meshtastic.util import findPorts
from serial.tools import list_ports
from zeroconf import IPVersion, ServiceBrowser, ServiceListener, Zeroconf

MESHTASTIC_SERVICE_TYPE = "_meshtastic._tcp.local."


def _decode_txt(properties: dict[bytes, bytes | None]) -> dict[str, str]:
    result = {}
    for raw_key, raw_value in properties.items():
        key = raw_key.decode("utf-8", errors="replace")
        value = (raw_value or b"").decode("utf-8", errors="replace")
        result[key] = value
    return result


def _neighbor_macs(path: Path | str = "/proc/net/arp") -> dict[str, str]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return {}
    result = {}
    for line in lines:
        columns = line.split()
        if len(columns) < 6:
            continue
        address, _, flags, mac = columns[:4]
        if flags != "0x2" or mac == "00:00:00:00:00:00":
            continue
        result[address] = mac.lower()
    return result


def _service_mac(addresses: list[str], properties: dict[str, str]) -> str | None:
    for key in ("mac", "mac_address", "macAddress"):
        value = properties.get(key)
        if value:
            return value.lower()
    neighbors = _neighbor_macs()
    return next((neighbors[address] for address in addresses if address in neighbors), None)


class _MeshtasticListener(ServiceListener):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._services: dict[str, dict[str, Any]] = {}

    def add_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        info = zeroconf.get_service_info(service_type, name, timeout=1200)
        if info is None:
            return
        addresses = info.parsed_scoped_addresses(IPVersion.V4Only)
        hostname = (info.server or "").rstrip(".")
        host = addresses[0] if addresses else hostname
        if not host:
            return
        properties = _decode_txt(info.properties)
        display_name = name.removesuffix(f".{service_type}").rstrip(".")
        service = {
            "name": display_name or hostname or host,
            "host": host,
            "hostname": hostname,
            "port": int(info.port or 4403),
            "addresses": addresses,
            "mac": _service_mac(addresses, properties),
            "node_id": properties.get("id") or None,
            "short_name": properties.get("shortname") or None,
            "platform": properties.get("pio_env") or None,
            "properties": properties,
        }
        with self._lock:
            self._services[name] = service

    def update_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        self.add_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        with self._lock:
            self._services.pop(name, None)

    def result(self) -> list[dict[str, Any]]:
        with self._lock:
            services = list(self._services.values())
        return sorted(services, key=lambda service: (service["name"].casefold(), service["host"]))


class TcpDiscovery:
    """Discover Meshtastic native TCP endpoints over DNS-SD/mDNS."""

    def discover(self, timeout: float = 3.0) -> list[dict[str, Any]]:
        if not 0.5 <= timeout <= 10:
            raise ValueError("Discovery timeout must be between 0.5 and 10 seconds")
        listener = _MeshtasticListener()
        zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        browser = ServiceBrowser(zeroconf, MESHTASTIC_SERVICE_TYPE, listener)
        try:
            threading.Event().wait(timeout)
            return listener.result()
        finally:
            browser.cancel()
            zeroconf.close()


class SerialDiscovery:
    """Project pyserial/Meshtastic candidates as operator-friendly USB endpoints."""

    def __init__(
        self,
        ports_factory: Callable[[], Iterable[Any]] | None = None,
        candidate_factory: Callable[[], Iterable[str]] | None = None,
        by_id_directory: Path | str = "/dev/serial/by-id",
        access_checker: Callable[[str, int], bool] = os.access,
    ) -> None:
        self._ports_factory = ports_factory or list_ports.comports
        self._candidate_factory = candidate_factory or (lambda: findPorts(True))
        self._by_id_directory = Path(by_id_directory)
        self._access_checker = access_checker

    def _stable_paths(self) -> dict[str, str]:
        try:
            entries = list(self._by_id_directory.iterdir())
        except OSError:
            return {}
        result = {}
        for entry in entries:
            try:
                result[str(entry.resolve())] = str(entry)
            except OSError:
                continue
        return result

    @staticmethod
    def _hex_identifier(value: Any) -> str | None:
        return f"{int(value):04x}" if isinstance(value, int) else None

    def discover(self) -> list[dict[str, Any]]:
        ports = {str(port.device): port for port in self._ports_factory()}
        stable_paths = self._stable_paths()
        devices = []
        for device in dict.fromkeys(str(path) for path in self._candidate_factory()):
            port = ports.get(device)
            stable_path = stable_paths.get(str(Path(device).resolve()))
            connection_path = stable_path or device
            accessible = self._access_checker(connection_path, os.R_OK | os.W_OK)
            devices.append(
                {
                    "device": device,
                    "connection_path": connection_path,
                    "stable_path": stable_path,
                    "description": getattr(port, "description", None) or "USB Serial device",
                    "manufacturer": getattr(port, "manufacturer", None),
                    "product": getattr(port, "product", None),
                    "serial_number": getattr(port, "serial_number", None),
                    "vid": self._hex_identifier(getattr(port, "vid", None)),
                    "pid": self._hex_identifier(getattr(port, "pid", None)),
                    "location": getattr(port, "location", None),
                    "hwid": getattr(port, "hwid", None),
                    "accessible": accessible,
                    "permission_hint": (
                        None
                        if accessible
                        else "Нужен е read/write достъп до порта (обикновено група dialout)."
                    ),
                }
            )
        return sorted(devices, key=lambda item: (not item["accessible"], item["device"]))
