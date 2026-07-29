from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

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
