from __future__ import annotations

import json
import threading
from datetime import UTC, datetime

from meshtastic.protobuf import channel_pb2, localonly_pb2, storeforward_pb2

from meshdesk.history import EncryptedHistory
from meshdesk.manager import MeshtasticManager


class FakeLocalNode:
    def __init__(self) -> None:
        self.localConfig = localonly_pb2.LocalConfig()
        self.moduleConfig = localonly_pb2.LocalModuleConfig()
        self.channels = []
        self.written = []
        self.owner_updates = []

    def writeConfig(self, section):
        self.written.append(section)

    def setFavorite(self, node_id):
        self.written.append(("favorite", node_id))
        return {"id": 85}

    def removeFavorite(self, node_id):
        self.written.append(("unfavorite", node_id))
        return {"id": 86}

    def setIgnored(self, node_id):
        self.written.append(("ignore", node_id))
        return {"id": 87}

    def removeIgnored(self, node_id):
        self.written.append(("unignore", node_id))
        return {"id": 88}

    def setOwner(self, **values):
        self.owner_updates.append(values)
        return {"id": 89}

    def reboot(self, secs):
        self.written.append(("reboot", secs))
        return {"id": 90}

    def shutdown(self, secs):
        self.written.append(("shutdown", secs))
        return {"id": 91}

    def factoryReset(self, full):
        self.written.append(("factory_reset", full))
        return {"id": 92}

    def resetNodeDb(self):
        self.written.append(("reset_nodedb",))
        return {"id": 93}


class FakeInterface:
    def __init__(self) -> None:
        self.localNode = FakeLocalNode()
        self.nodes = {
            "!12345678": {
                "num": 0x12345678,
                "user": {
                    "id": "!12345678",
                    "longName": "Test Node",
                    "shortName": "TEST",
                    "hwModel": "TBEAM",
                },
                "lastHeard": 1_700_000_000,
                "snr": 8.5,
                "hopsAway": 0,
                "viaMqtt": False,
                "deviceMetrics": {"batteryLevel": 88, "voltage": 4.1},
                "position": {"latitude": 42.1, "longitude": 23.2},
            }
        }
        self.sent = []
        self.sent_data = []
        self.remote_node = FakeLocalNode()
        self.ack_waits = 0

    def getMyNodeInfo(self):
        return next(iter(self.nodes.values()))

    def sendText(self, text, **kwargs):
        self.sent.append((text, kwargs))
        return {"id": 42}

    def sendData(self, payload, **kwargs):
        self.sent_data.append((payload, kwargs))
        return {"id": 84}

    def getNode(self, node_id, requestChannels=False, timeout=45):
        return self.remote_node

    def waitForAckNak(self):
        self.ack_waits += 1

    def close(self):
        return None


def connected_manager() -> tuple[MeshtasticManager, FakeInterface]:
    manager = MeshtasticManager()
    interface = FakeInterface()
    manager._interface = interface  # noqa: SLF001 - deliberate unit-test seam
    manager._state = "connected"  # noqa: SLF001
    return manager, interface


def test_nodes_are_projected_for_the_ui():
    manager, _ = connected_manager()
    node = manager.nodes()[0]
    assert node["id"] == "!12345678"
    assert node["long_name"] == "Test Node"
    assert node["battery_level"] == 88
    assert node["hops_away"] == 0
    assert node["via_mqtt"] is False
    assert node["latitude"] == 42.1
    assert node["is_messageable"] is True


def test_send_text_records_packet_and_event():
    manager, interface = connected_manager()
    packet = manager.send_text("hello", "!12345678", 2, True)
    assert packet == {"id": 42}
    text, kwargs = interface.sent[0]
    assert text == "hello"
    assert kwargs["destinationId"] == "!12345678"
    assert kwargs["channelIndex"] == 2
    assert kwargs["wantAck"] is True
    assert manager.events()[0]["want_ack"] is True
    kwargs["onResponse"](
        {"decoded": {"requestId": 42, "routing": {"errorReason": "NONE"}}}
    )
    assert manager.events()[0]["kind"] == "outgoing"
    assert manager.events()[1]["kind"] == "delivery"


def test_connection_health_distinguishes_manual_disconnect_and_loss():
    manager, interface = connected_manager()
    manager._transport = "tcp"  # noqa: SLF001
    manager._target = "172.16.19.176:4403"  # noqa: SLF001
    manager._connected_at = datetime.now(UTC).isoformat()  # noqa: SLF001

    manager.disconnect()
    manual = manager.status()["health"]
    assert manual["state"] == "disconnected"
    assert manual["reason"] == "manual"
    assert manual["target"] == "172.16.19.176:4403"
    assert manual["reconnect_eligible"] is False

    manager._interface = interface  # noqa: SLF001
    manager._state = "connected"  # noqa: SLF001
    manager._transport = "tcp"  # noqa: SLF001
    manager._target = "172.16.19.176:4403"  # noqa: SLF001
    manager._on_connection_lost(interface)  # noqa: SLF001
    lost = manager.status()["health"]
    assert lost["state"] == "lost"
    assert lost["reason"] == "connection_lost"
    assert lost["reconnect_eligible"] is True


def test_receive_updates_health_activity_timestamps():
    manager, interface = connected_manager()
    assert manager.status()["health"]["last_rx_at"] is None

    manager._on_receive(  # noqa: SLF001
        {
            "fromId": "!87654321",
            "toId": "^all",
            "channel": 0,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "health"},
        },
        interface,
    )

    health = manager.status()["health"]
    assert health["state"] == "healthy"
    assert health["last_rx_at"] is not None
    assert datetime.fromisoformat(health["last_activity_at"]) >= datetime.fromisoformat(
        health["last_rx_at"]
    )


def test_connection_errors_are_classified_for_reconnect_policy():
    assert (
        MeshtasticManager._classify_connection_error(  # noqa: SLF001
            TimeoutError("handshake timed out"),
            "tcp",
        )
        == "timeout"
    )
    assert (
        MeshtasticManager._classify_connection_error(  # noqa: SLF001
            RuntimeError("Not paired"),
            "ble",
        )
        == "pairing_required"
    )


def test_message_history_is_scoped_to_active_radio_profile(tmp_path):
    history = EncryptedHistory(tmp_path / "logs", key=b"h" * 32)
    manager = MeshtasticManager(history=history)
    interface = FakeInterface()
    manager._interface = interface  # noqa: SLF001
    manager._state = "connected"  # noqa: SLF001
    manager._profile_id = "!aaaaaaaa"  # noqa: SLF001

    manager.send_text("profile A")

    assert history.load("!aaaaaaaa")[0]["text"] == "profile A"
    assert history.load("!bbbbbbbb") == []


def test_send_text_validates_utf8_payload_size():
    manager, _ = connected_manager()
    try:
        manager.send_text("я" * 116)
    except ValueError as exc:
        assert "230" in str(exc)
    else:
        raise AssertionError("Expected message length validation")


def test_node_diagnostic_actions_record_requests_and_responses():
    manager, interface = connected_manager()
    packet = manager.request_node_action("!12345678", "telemetry", 1, "environment", 4)
    assert packet == {"id": 84}
    _, kwargs = interface.sent_data[0]
    assert kwargs["destinationId"] == "!12345678"
    assert kwargs["channelIndex"] == 1
    assert kwargs["hopLimit"] == 4
    assert manager.events()[0]["kind"] == "operation_request"

    kwargs["onResponse"](
        {
            "from": 0x12345678,
            "to": 0x87654321,
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {"environmentMetrics": {"temperature": 21.5}},
            },
        }
    )
    result = manager.events()[1]
    assert result["kind"] == "operation_result"
    assert result["success"] is True
    assert result["result"]["telemetry"]["environmentMetrics"]["temperature"] == 21.5


def test_node_management_action_updates_local_nodedb():
    manager, interface = connected_manager()
    packet = manager.request_node_action("!12345678", "favorite")
    assert packet == {"id": 85}
    assert interface.localNode.written == [("favorite", "!12345678")]
    assert manager.events()[0]["operation"] == "favorite"


def test_traceroute_response_is_projected_as_hops_with_snr():
    manager, interface = connected_manager()
    manager.request_node_action("!12345678", "traceroute", hop_limit=3)
    _, kwargs = interface.sent_data[0]
    kwargs["onResponse"](
        {
            "from": 0x12345678,
            "to": 0x87654321,
            "hopStart": 3,
            "decoded": {
                "portnum": "TRACEROUTE_APP",
                "traceroute": {
                    "route": [0x22222222],
                    "snrTowards": [8, 12],
                    "routeBack": [0x33333333],
                    "snrBack": [4, 8],
                },
            },
        }
    )
    result = manager.events()[1]["result"]
    assert [hop["id"] for hop in result["route_towards"]] == [
        "!87654321",
        "!22222222",
        "!12345678",
    ]
    assert result["route_towards"][-1]["snr"] == 3
    assert result["route_back"][-1]["snr"] == 2


def test_incoming_direct_text_has_conversation_metadata():
    manager, interface = connected_manager()
    manager._on_receive(  # noqa: SLF001 - exercise pubsub projection directly
        {
            "fromId": "!12345678",
            "toId": "!87654321",
            "channel": 1,
            "decoded": {"text": "private hello", "portnum": "TEXT_MESSAGE_APP"},
        },
        interface,
    )
    event = manager.events()[0]
    assert event["is_direct"] is True
    assert event["conversation"] == "direct:!12345678"


def test_disconnect_does_not_hang_on_broken_transport(monkeypatch):
    manager, interface = connected_manager()
    never_finishes = threading.Event()
    interface.close = never_finishes.wait
    monkeypatch.setattr("meshdesk.manager.INTERFACE_CLOSE_TIMEOUT", 0.01)
    manager.disconnect()
    assert manager.status()["state"] == "disconnected"


def test_channels_include_only_enabled_channels():
    manager, interface = connected_manager()
    primary = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    primary.settings.name = "LongFast"
    primary.settings.psk = b"\x01"
    disabled = channel_pb2.Channel(index=1, role=channel_pb2.Channel.Role.DISABLED)
    interface.localNode.channels = [primary, disabled]
    assert manager.channels() == [
        {
            "index": 0,
            "name": "LongFast",
            "role": "PRIMARY",
            "uplink_enabled": False,
            "downlink_enabled": False,
            "position_precision": 0,
            "encrypted": True,
        }
    ]


def test_config_schema_hides_secret_and_updates_section():
    manager, interface = connected_manager()
    interface.localNode.localConfig.bluetooth.enabled = True
    interface.localNode.localConfig.bluetooth.fixed_pin = 123456
    interface.localNode.localConfig.display.units = 28
    config = manager.config()
    json.dumps(config)
    bluetooth = next(item for item in config["sections"] if item["name"] == "bluetooth")
    fixed_pin = next(item for item in bluetooth["fields"] if item["name"] == "fixed_pin")
    assert fixed_pin["value"] == ""
    assert fixed_pin["secret"] is True
    display = next(item for item in config["sections"] if item["name"] == "display")
    units = next(item for item in display["fields"] if item["name"] == "units")
    assert units["value"] == "UNKNOWN (28)"
    assert "UNKNOWN (28)" in units["enum_values"]

    manager.update_config("bluetooth", {"enabled": False, "fixed_pin": ""})
    assert interface.localNode.localConfig.bluetooth.enabled is False
    assert interface.localNode.localConfig.bluetooth.fixed_pin == 123456
    assert interface.localNode.written == ["bluetooth"]


def test_safe_config_export_and_import_omit_secrets():
    manager, interface = connected_manager()
    interface.localNode.localConfig.bluetooth.enabled = True
    interface.localNode.localConfig.bluetooth.fixed_pin = 123456

    exported = manager.export_config()
    bluetooth = exported["sections"]["bluetooth"]
    assert bluetooth["enabled"] is True
    assert "fixed_pin" not in bluetooth

    result = manager.import_config(
        {
            "format": "meshdesk-config-v1",
            "sections": {"bluetooth": {"enabled": False}},
        }
    )
    assert result == {"written": ["bluetooth"]}
    assert interface.localNode.localConfig.bluetooth.enabled is False


def test_owner_section_updates_long_and_short_name():
    manager, interface = connected_manager()
    owner = manager.config()["sections"][0]
    assert owner["name"] == "owner"
    values = {field["name"]: field["value"] for field in owner["fields"]}
    assert values["long_name"] == "Test Node"
    assert values["short_name"] == "TEST"

    manager.update_config(
        "owner",
        {"long_name": "Base Station", "short_name": "BASE"},
    )
    assert interface.localNode.owner_updates == [
        {
            "long_name": "Base Station",
            "short_name": "BASE",
            "is_licensed": False,
            "is_unmessagable": False,
        }
    ]


def test_remote_nodedb_preference_uses_managed_remote_node():
    manager, interface = connected_manager()
    manager.request_node_action(
        "!12345678",
        "ignore",
        managed_node_id="!87654321",
    )
    assert interface.localNode.written == []
    assert interface.remote_node.written == [("ignore", "!12345678")]
    assert interface.ack_waits == 1


def test_history_replay_matches_android_client_request():
    manager, interface = connected_manager()
    manager._profile_id = "!12345678"  # noqa: SLF001
    packet = manager.request_history_replay(120, 25)
    assert packet == {"id": 84}
    payload, kwargs = interface.sent_data[0]
    assert isinstance(payload, storeforward_pb2.StoreAndForward)
    assert payload.rr == storeforward_pb2.StoreAndForward.CLIENT_HISTORY
    assert payload.history.window == 120
    assert payload.history.history_messages == 25
    assert payload.history.last_request == 0
    assert kwargs["destinationId"] == "!12345678"
    assert kwargs["wantAck"] is False


def test_store_forward_text_becomes_recovered_chat_message():
    manager, interface = connected_manager()
    replay = storeforward_pb2.StoreAndForward(
        rr=storeforward_pb2.StoreAndForward.ROUTER_TEXT_BROADCAST,
        text=b"missed hello",
    )
    manager._on_receive(  # noqa: SLF001
        {
            "fromId": "!12345678",
            "toId": "!ffffffff",
            "channel": 2,
            "decoded": {
                "portnum": "STORE_FORWARD_APP",
                "storeforward": {"rr": "ROUTER_TEXT_BROADCAST", "raw": replay},
            },
        },
        interface,
    )
    event = manager.events()[0]
    assert event["kind"] == "incoming"
    assert event["text"] == "missed hello"
    assert event["conversation"] == "channel:2"
    assert event["recovered"] is True


def test_history_status_marks_following_local_text_as_recovered():
    manager, interface = connected_manager()
    manager._history_replay_requested_at = 1_700_000_100  # noqa: SLF001
    history = storeforward_pb2.StoreAndForward(
        rr=storeforward_pb2.StoreAndForward.ROUTER_HISTORY,
        history=storeforward_pb2.StoreAndForward.History(
            history_messages=1,
            last_request=12,
        ),
    )
    manager._on_receive(  # noqa: SLF001
        {
            "fromId": "!12345678",
            "decoded": {
                "portnum": "STORE_FORWARD_APP",
                "storeforward": {"rr": "ROUTER_HISTORY", "raw": history},
            },
        },
        interface,
    )
    manager._on_receive(  # noqa: SLF001
        {
            "fromId": "!87654321",
            "toId": "^all",
            "rxTime": 1_700_000_000,
            "channel": 0,
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": "local replay",
            },
        },
        interface,
    )
    event = manager.events()[1]
    assert event["text"] == "local replay"
    assert event["recovered"] is True


def test_packets_arriving_during_handshake_are_buffered():
    manager = MeshtasticManager()
    interface = FakeInterface()
    manager._state = "connecting"  # noqa: SLF001
    packet = {
        "fromId": "!12345678",
        "toId": "^all",
        "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "handshake backlog"},
    }
    manager._on_receive(packet, interface)  # noqa: SLF001
    assert manager.events() == []
    assert manager._pending_receive_packets == [(interface, packet)]  # noqa: SLF001

    manager._interface = interface  # noqa: SLF001
    manager._state = "connected"  # noqa: SLF001
    manager._on_receive(packet, interface)  # noqa: SLF001
    assert manager.events()[0]["text"] == "handshake backlog"
