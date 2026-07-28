from __future__ import annotations

from fastapi.testclient import TestClient

from meshdesk.app import create_app


class StubManager:
    def __init__(self):
        self.calls = []

    def status(self):
        return {"state": "disconnected", "event_sequence": 0}

    def connect_tcp(self, host, port):
        self.calls.append(("tcp", host, port))

    def connect_ble(self, address):
        self.calls.append(("ble", address))

    def disconnect(self):
        self.calls.append(("disconnect",))

    def scan_ble(self):
        return [{"name": "Mesh", "address": "AA:BB"}]

    def nodes(self):
        return []

    def events(self, after):
        return [{"seq": after + 1}]

    def send_text(self, text, destination, channel, want_ack):
        self.calls.append(("send", text, destination, channel, want_ack))
        return {"id": 7}

    def request_node_action(self, node_id, action, channel, telemetry_type, hop_limit):
        self.calls.append(
            ("node_action", node_id, action, channel, telemetry_type, hop_limit)
        )
        return {"id": 9}

    def history(self):
        return [{"event_id": "saved-1", "kind": "incoming"}]

    def request_remote_config(self, node_id, section):
        self.calls.append(("remote_config", node_id, section))


def test_tcp_connection_endpoint():
    manager = StubManager()
    with TestClient(create_app(manager)) as client:
        response = client.post(
            "/api/connect",
            json={"transport": "tcp", "host": "172.16.19.176", "port": 4403},
        )
    assert response.status_code == 202
    assert manager.calls[0] == ("tcp", "172.16.19.176", 4403)


def test_send_message_endpoint():
    manager = StubManager()
    with TestClient(create_app(manager)) as client:
        response = client.post(
            "/api/messages",
            json={"text": "test", "destination": "^all", "channel": 0, "want_ack": True},
        )
    assert response.json() == {"packet": {"id": 7}}
    assert manager.calls[0] == ("send", "test", "^all", 0, True)


def test_node_action_endpoint():
    manager = StubManager()
    with TestClient(create_app(manager)) as client:
        response = client.post(
            "/api/node-actions",
            json={
                "node_id": "!12345678",
                "action": "traceroute",
                "channel": 1,
                "hop_limit": 4,
            },
        )
    assert response.status_code == 202
    assert response.json() == {"packet": {"id": 9}}
    assert manager.calls[0] == (
        "node_action",
        "!12345678",
        "traceroute",
        1,
        "device",
        4,
    )


def test_history_and_remote_config_endpoints():
    manager = StubManager()
    with TestClient(create_app(manager)) as client:
        history = client.get("/api/history")
        remote = client.post(
            "/api/remote-admin/config",
            json={"node_id": "!12345678", "section": "lora"},
        )
    assert history.json()["events"][0]["event_id"] == "saved-1"
    assert remote.status_code == 202
    assert manager.calls[0] == ("remote_config", "!12345678", "lora")
