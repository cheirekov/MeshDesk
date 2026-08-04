from __future__ import annotations

import io
import json
import time

import pytest

from meshdesk.packet_observers import PacketObserverService


class ConnectedRadio:
    def __init__(self):
        self.observer_events = []

    def status(self):
        return {
            "state": "connected",
            "transport": "ble",
            "target": "AA:BB:CC:DD:EE:FF",
            "profile_id": "!a1b3b3b8",
            "profile_name": "nemo",
        }

    def record_observer_sighting(self, **event):
        self.observer_events.append(event)


class FakeProcess:
    def __init__(self, records):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(
            "".join(json.dumps(record) + "\n" for record in records)
        )
        self.terminated = False

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


def observer_profile(enabled=True):
    return {
        "id": "gateway",
        "name": "Tarnovo observer",
        "transport": "tcp",
        "host": "172.16.16.115",
        "port": 4403,
        "device_id": "!8fd13c64",
        "diagnostic_observer": enabled,
    }


def test_bounded_observer_correlates_packet_metadata_without_payload():
    records = [
        {"kind": "ready", "node_id": "!8fd13c64"},
        {
            "kind": "packet",
            "seen_at": "2026-08-04T12:00:00+00:00",
            "packet_id": 3403877,
            "from": "!a1b3b3b8",
            "to": "^all",
            "channel": 1,
            "portnum": "TEXT_MESSAGE_APP",
            "via_mqtt": False,
            "snr": 4.5,
            "rssi": -91,
        },
        {"kind": "complete"},
    ]
    service = PacketObserverService(
        launcher=lambda _profile, _request: FakeProcess(records)
    )
    radio = ConnectedRadio()

    service.start([observer_profile()], radio, 30)
    deadline = time.monotonic() + 1
    while service.status()["state"] not in {"completed", "stopped"}:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    status = service.status()

    assert status["sightings"][0]["packet_id"] == 3403877
    assert status["sightings"][0]["observers"][0]["profile_name"] == (
        "Tarnovo observer"
    )
    assert status["sightings"][0]["observers"][0]["via_mqtt"] is False
    assert "payload" not in str(status).lower()
    assert radio.observer_events[0]["packet_id"] == 3403877
    assert radio.observer_events[0]["observer_profile_name"] == "Tarnovo observer"


def test_observer_requires_explicitly_selected_verified_tcp_profile():
    service = PacketObserverService(
        launcher=lambda _profile, _request: FakeProcess([])
    )

    with pytest.raises(ValueError, match="No eligible"):
        service.start([observer_profile(enabled=False)], ConnectedRadio(), 30)
