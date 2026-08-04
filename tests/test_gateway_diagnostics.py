from __future__ import annotations

import base64

from meshdesk.gateway_diagnostics import GatewayDiagnostics, channel_signature


class DiagnosticRadio:
    def gateway_diagnostic_context(self, nonce: bytes) -> dict:
        return {
            "subject_node_id": "!a1b3b3b8",
            "subject_name": "nemo",
            "transport": "ble",
            "radio": {"region": "EU_868", "modem_preset": "MEDIUM_FAST"},
            "channels": [
                {
                    "index": 1,
                    "role": "SECONDARY",
                    "enabled": True,
                    "name": "Bulgaria",
                    "signature": channel_signature(
                        nonce,
                        1,
                        2,
                        "Bulgaria",
                        b"shared-key",
                    ),
                }
            ],
        }


def test_gateway_probe_compares_identity_radio_channel_and_subject_observation():
    def worker(_profile, request):
        nonce = base64.b64decode(request["nonce"])
        return {
            "status": "reachable",
            "node_id": "!8fd1336c",
            "long_name": "gorna2",
            "radio": {"region": "EU_868", "modem_preset": "MEDIUM_FAST"},
            "network": {"udp_broadcast_enabled": False, "mqtt_enabled": True},
            "channels": [
                {
                    "index": 1,
                    "role": "SECONDARY",
                    "enabled": True,
                    "name": "Bulgaria",
                    "uplink_enabled": True,
                    "downlink_enabled": True,
                    "signature": channel_signature(
                        nonce,
                        1,
                        2,
                        "Bulgaria",
                        b"shared-key",
                    ),
                }
            ],
            "subject_observation": {
                "last_heard": "2026-08-04T08:54:20+00:00",
                "hops_away": 2,
                "via_mqtt": True,
            },
        }

    profiles = [
        {
            "id": "gateway",
            "name": "Home gateway",
            "transport": "tcp",
            "host": "172.16.19.176",
            "port": 4403,
            "device_id": "!8fd1336c",
            "diagnostic_observer": True,
        },
        {
            "id": "active",
            "name": "Nemo over TCP",
            "transport": "tcp",
            "host": "nemo.local",
            "port": 4403,
            "device_id": "!a1b3b3b8",
            "diagnostic_observer": True,
        },
        {
            "id": "ble",
            "name": "BLE profile",
            "transport": "ble",
            "address": "00:11:22:33:44:55",
        },
    ]
    diagnostics = GatewayDiagnostics(probe_worker=worker)

    result = diagnostics.probe(profiles, DiagnosticRadio())

    assert result["summary"] == {
        "available_tcp_profiles": 2,
        "selected_observers": 2,
        "reachable": 1,
        "observed_subject": 1,
    }
    gateway, active = result["gateways"]
    assert gateway["identity"]["match"] is True
    assert gateway["compatibility"]["verdict"] == "compatible"
    assert gateway["compatibility"]["matching_channel_count"] == 1
    assert "signature" not in gateway["channels"][0]
    assert active["status"] == "skipped"
    assert active["error_code"] == "active_device"


def test_gateway_probe_isolates_worker_failure():
    def worker(_profile, _request):
        raise RuntimeError("sensitive transport detail")

    diagnostics = GatewayDiagnostics(probe_worker=worker)
    result = diagnostics.probe(
        [
            {
                "id": "gateway",
                "name": "Gateway",
                "transport": "tcp",
                "host": "unreachable.local",
                "port": 4403,
                "device_id": "!8fd1336c",
                "diagnostic_observer": True,
            }
        ],
        DiagnosticRadio(),
    )

    assert result["gateways"][0]["status"] == "unreachable"
    assert result["gateways"][0]["error_code"] == "probe_failed"
    assert "sensitive" not in result["gateways"][0]["error"]


def test_gateway_probe_excludes_tcp_profiles_without_explicit_opt_in():
    calls = []

    def worker(profile, _request):
        calls.append(profile["id"])
        return {"status": "reachable", "node_id": profile["device_id"]}

    diagnostics = GatewayDiagnostics(probe_worker=worker)
    result = diagnostics.probe(
        [
            {
                "id": "ordinary-profile",
                "name": "Ordinary TCP radio",
                "transport": "tcp",
                "host": "ordinary.local",
                "port": 4403,
                "device_id": "!8fd1336c",
                "diagnostic_observer": False,
            }
        ],
        DiagnosticRadio(),
    )

    assert calls == []
    assert result["gateways"] == []
    assert result["summary"]["available_tcp_profiles"] == 1
    assert result["summary"]["selected_observers"] == 0
