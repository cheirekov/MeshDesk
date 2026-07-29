from __future__ import annotations

import pytest

from meshdesk.discovery import (
    MESHTASTIC_SERVICE_TYPE,
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
