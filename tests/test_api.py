from __future__ import annotations

from fastapi.testclient import TestClient

from meshdesk.app import create_app
from meshdesk.connection_profiles import ConnectionProfileStore


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

    def channels(self):
        return []

    def channel_slots(self):
        return [
            {
                "index": 0,
                "name": "Main",
                "display_name": "Main",
                "role": "PRIMARY",
            }
        ]

    def channel_psk(self, index):
        self.calls.append(("channel_psk", index))
        return {
            "index": index,
            "psk_base64": "AQ==",
            "psk_state": "default",
            "byte_length": 1,
            "publicly_known": True,
            "encrypted": True,
        }

    def update_channel(
        self,
        index,
        role,
        name,
        psk_mode,
        psk,
        uplink,
        downlink,
        position_precision,
    ):
        self.calls.append(
            (
                "channel",
                index,
                role,
                name,
                psk_mode,
                psk,
                uplink,
                downlink,
                position_precision,
            )
        )
        return self.channel_slots()

    def events(self, after):
        return [{"seq": after + 1}]

    def send_text(self, text, destination, channel, want_ack):
        self.calls.append(("send", text, destination, channel, want_ack))
        return {"id": 7}

    def request_node_action(
        self,
        node_id,
        action,
        channel,
        telemetry_type,
        hop_limit,
        managed_node_id,
    ):
        self.calls.append(
            (
                "node_action",
                node_id,
                action,
                channel,
                telemetry_type,
                hop_limit,
                managed_node_id,
            )
        )
        return {"id": 9}

    def history(self):
        return [{"event_id": "saved-1", "kind": "incoming"}]

    def request_remote_config(self, node_id, section):
        self.calls.append(("remote_config", node_id, section))

    def request_history_replay(self, window, maximum):
        self.calls.append(("history_replay", window, maximum))
        return {"id": 10}

    def request_admin_action(self, action, node_id, preserve):
        self.calls.append(("administration", action, node_id, preserve))


class ConnectedIdentityManager(StubManager):
    def __init__(self):
        super().__init__()
        self.device_id = "!1234abcd"
        self.device_name = "Test Gateway"

    def status(self):
        return {
            "state": "connected",
            "transport": "tcp",
            "target": "172.16.19.176:4403",
            "profile_id": self.device_id,
            "profile_name": self.device_name,
            "event_sequence": 0,
        }


class StubTcpDiscovery:
    def __init__(self):
        self.timeouts = []

    def discover(self, timeout):
        self.timeouts.append(timeout)
        return [
            {
                "name": "Home Gateway",
                "host": "172.16.19.176",
                "hostname": "meshtastic.local",
                "port": 4403,
                "addresses": ["172.16.19.176"],
            }
        ]


def test_tcp_connection_endpoint():
    manager = StubManager()
    with TestClient(create_app(manager)) as client:
        response = client.post(
            "/api/connect",
            json={"transport": "tcp", "host": "172.16.19.176", "port": 4403},
        )
    assert response.status_code == 202
    assert manager.calls[0] == ("tcp", "172.16.19.176", 4403)


def test_tcp_mdns_discovery_endpoint():
    manager = StubManager()
    discovery = StubTcpDiscovery()
    with TestClient(create_app(manager, tcp_discovery=discovery)) as client:
        response = client.get("/api/discovery/tcp?timeout=1.5")

    assert response.status_code == 200
    assert response.json()["devices"][0]["host"] == "172.16.19.176"
    assert discovery.timeouts == [1.5]


def test_connection_profile_crud_and_usage(tmp_path):
    manager = StubManager()
    store = ConnectionProfileStore(tmp_path / "connection-profiles.json")
    with TestClient(create_app(manager, store)) as client:
        created = client.post(
            "/api/connection-profiles",
            json={
                "name": "Домашна база",
                "transport": "tcp",
                "host": "172.16.19.176",
                "port": 4403,
            },
        )
        profile = created.json()["profile"]
        listing = client.get("/api/connection-profiles")
        connected = client.post(
            "/api/connect",
            json={
                "transport": "tcp",
                "host": "172.16.19.176",
                "port": 4403,
                "connection_profile_id": profile["id"],
            },
        )
        deleted = client.delete(f"/api/connection-profiles/{profile['id']}")

    assert created.status_code == 201
    assert listing.json()["profiles"][0]["name"] == "Домашна база"
    assert connected.status_code == 202
    assert store.path.exists()
    assert deleted.status_code == 204
    assert store.list() == []


def test_saved_profile_cannot_be_attributed_to_another_endpoint(tmp_path):
    manager = StubManager()
    store = ConnectionProfileStore(tmp_path / "connection-profiles.json")
    profile = store.create(
        {
            "name": "Домашна база",
            "transport": "tcp",
            "host": "172.16.19.176",
            "port": 4403,
        }
    )

    with TestClient(create_app(manager, store)) as client:
        response = client.post(
            "/api/connect",
            json={
                "transport": "tcp",
                "host": "another-host.local",
                "port": 4403,
                "connection_profile_id": profile["id"],
            },
        )

    assert response.status_code == 409
    assert ("tcp", "another-host.local", 4403) not in manager.calls


def test_connection_profile_identity_verification_and_rebind(tmp_path):
    manager = ConnectedIdentityManager()
    store = ConnectionProfileStore(tmp_path / "connection-profiles.json")
    profile = store.create(
        {
            "name": "Домашна база",
            "transport": "tcp",
            "host": "172.16.19.176",
            "port": 4403,
        }
    )

    with TestClient(create_app(manager, store)) as client:
        verified = client.post(
            f"/api/connection-profiles/{profile['id']}/verify",
            json={"allow_rebind": False},
        )
        manager.device_id = "!87654321"
        manager.device_name = "Replacement"
        mismatch = client.post(
            f"/api/connection-profiles/{profile['id']}/verify",
            json={"allow_rebind": False},
        )
        rebound = client.post(
            f"/api/connection-profiles/{profile['id']}/verify",
            json={"allow_rebind": True},
        )

    assert verified.status_code == 200
    assert verified.json()["profile"]["device_id"] == "!1234abcd"
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "identity_mismatch"
    assert mismatch.json()["detail"]["expected_id"] == "!1234abcd"
    assert mismatch.json()["detail"]["observed_id"] == "!87654321"
    assert rebound.json()["profile"]["device_id"] == "!87654321"


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
        None,
    )


def test_channel_manager_endpoints():
    manager = StubManager()
    with TestClient(create_app(manager)) as client:
        listing = client.get("/api/channel-slots")
        revealed = client.get("/api/channel-slots/0/psk")
        updated = client.put(
            "/api/channel-slots/1",
            json={
                "role": "SECONDARY",
                "name": "Ops",
                "psk_mode": "random",
                "uplink_enabled": True,
                "downlink_enabled": False,
                "position_precision": 12,
            },
        )

    assert listing.status_code == 200
    assert listing.json()["channels"][0]["role"] == "PRIMARY"
    assert revealed.status_code == 200
    assert revealed.json()["psk_base64"] == "AQ=="
    assert revealed.headers["cache-control"] == "no-store, max-age=0"
    assert revealed.headers["pragma"] == "no-cache"
    assert updated.status_code == 200
    assert manager.calls[0] == ("channel_psk", 0)
    assert manager.calls[1] == (
        "channel",
        1,
        "SECONDARY",
        "Ops",
        "random",
        "",
        True,
        False,
        12,
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


def test_history_replay_and_administration_endpoints():
    manager = StubManager()
    with TestClient(create_app(manager)) as client:
        history = client.post(
            "/api/history/replay",
            json={"window_minutes": 120, "max_messages": 25},
        )
        administration = client.post(
            "/api/administration",
            json={
                "action": "reset_nodedb",
                "preserve_node_preferences": True,
            },
        )
    assert history.status_code == 202
    assert administration.status_code == 202
    assert manager.calls[:2] == [
        ("history_replay", 120, 25),
        ("administration", "reset_nodedb", None, True),
    ]
