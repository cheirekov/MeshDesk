from __future__ import annotations

from types import SimpleNamespace

import pytest

from meshdesk.discovery import (
    MESHTASTIC_SERVICE_TYPE,
    SerialDiscovery,
    TcpDiscovery,
    _MeshtasticListener,
    _neighbor_macs,
)


class FakeServiceInfo:
    server = "meshtastic.local."
    port = 4403
    properties = {
        b"mac": b"aa:bb:cc:dd:ee:ff",
        b"firmware": b"2.7.8",
        b"id": b"!1234abcd",
        b"shortname": b"ABCD",
        b"pio_env": b"seeed-xiao-s3",
    }

    @staticmethod
    def parsed_scoped_addresses(_version):
        return ["172.16.19.176"]


class FakeZeroconf:
    @staticmethod
    def get_service_info(_service_type, _name, timeout):
        assert timeout == 1200
        return FakeServiceInfo()


def test_mdns_service_is_projected_as_tcp_endpoint():
    listener = _MeshtasticListener()
    listener.add_service(
        FakeZeroconf(),
        MESHTASTIC_SERVICE_TYPE,
        f"Home Gateway.{MESHTASTIC_SERVICE_TYPE}",
    )

    assert listener.result() == [
        {
            "name": "Home Gateway",
            "host": "172.16.19.176",
            "hostname": "meshtastic.local",
            "port": 4403,
            "addresses": ["172.16.19.176"],
            "mac": "aa:bb:cc:dd:ee:ff",
            "node_id": "!1234abcd",
            "short_name": "ABCD",
            "platform": "seeed-xiao-s3",
            "properties": {
                "mac": "aa:bb:cc:dd:ee:ff",
                "firmware": "2.7.8",
                "id": "!1234abcd",
                "shortname": "ABCD",
                "pio_env": "seeed-xiao-s3",
            },
        }
    ]


def test_mdns_timeout_is_bounded():
    with pytest.raises(ValueError, match="between 0.5 and 10"):
        TcpDiscovery().discover(0.1)


def test_neighbor_mac_parser_ignores_incomplete_entries(tmp_path):
    table = tmp_path / "arp"
    table.write_text(
        "IP address HW type Flags HW address Mask Device\n"
        "172.16.19.176 0x1 0x2 aa:bb:cc:dd:ee:ff * eth0\n"
        "172.16.19.177 0x1 0x0 00:00:00:00:00:00 * eth0\n",
        encoding="utf-8",
    )

    assert _neighbor_macs(table) == {"172.16.19.176": "aa:bb:cc:dd:ee:ff"}


def test_serial_discovery_prefers_stable_by_id_path(tmp_path):
    device = tmp_path / "dev" / "ttyACM0"
    device.parent.mkdir()
    device.touch()
    by_id = tmp_path / "by-id"
    by_id.mkdir()
    stable = by_id / "usb-Meshtastic_ABC-if00"
    stable.symlink_to(device)
    port = SimpleNamespace(
        device=str(device),
        description="Meshtastic CDC",
        manufacturer="Meshtastic",
        product="T-Beam",
        serial_number="ABC",
        vid=0x303A,
        pid=0x1001,
        location="1-2",
        hwid="USB VID:PID=303A:1001",
    )

    devices = SerialDiscovery(
        ports_factory=lambda: [port],
        candidate_factory=lambda: [str(device)],
        by_id_directory=by_id,
        access_checker=lambda _path, _mode: True,
    ).discover()

    assert devices[0]["device"] == str(device)
    assert devices[0]["connection_path"] == str(stable)
    assert devices[0]["stable_path"] == str(stable)
    assert devices[0]["vid"] == "303a"
    assert devices[0]["pid"] == "1001"
    assert devices[0]["accessible"] is True


def test_serial_discovery_reports_missing_permissions(tmp_path):
    device = "/dev/ttyUSB9"
    port = SimpleNamespace(
        device=device,
        description="USB UART",
        manufacturer=None,
        product=None,
        serial_number=None,
        vid=0x10C4,
        pid=0xEA60,
        location=None,
        hwid="USB VID:PID=10C4:EA60",
    )

    result = SerialDiscovery(
        ports_factory=lambda: [port],
        candidate_factory=lambda: [device],
        by_id_directory=tmp_path / "missing",
        access_checker=lambda _path, _mode: False,
    ).discover()[0]

    assert result["connection_path"] == device
    assert result["accessible"] is False
    assert "dialout" in result["permission_hint"]
