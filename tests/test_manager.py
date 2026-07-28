from __future__ import annotations

import json
import threading

from meshtastic.protobuf import channel_pb2, localonly_pb2

from meshdesk.history import EncryptedHistory
from meshdesk.manager import MeshtasticManager


class FakeLocalNode:
    def __init__(self) -> None:
        self.localConfig = localonly_pb2.LocalConfig()
        self.moduleConfig = localonly_pb2.LocalModuleConfig()
        self.channels = []
        self.written = []

    def writeConfig(self, section):
        self.written.append(section)

    def setFavorite(self, node_id):
        self.written.append(("favorite", node_id))
        return {"id": 85}


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

    def getMyNodeInfo(self):
        return next(iter(self.nodes.values()))

    def sendText(self, text, **kwargs):
        self.sent.append((text, kwargs))
        return {"id": 42}

    def sendData(self, payload, **kwargs):
        self.sent_data.append((payload, kwargs))
        return {"id": 84}

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
