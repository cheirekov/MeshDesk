from __future__ import annotations

import base64
import json
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from meshtastic.protobuf import (
    admin_pb2,
    channel_pb2,
    config_pb2,
    localonly_pb2,
    mesh_pb2,
    portnums_pb2,
    storeforward_pb2,
)
from meshtastic.util import to_node_num

from meshdesk.history import EncryptedHistory
from meshdesk.manager import (
    CapabilityUnsupportedError,
    DeviceIdentityMismatchError,
    MeshtasticManager,
    RequestCooldownError,
)


class FakeLocalNode:
    def __init__(self) -> None:
        self.nodeNum = 0x87654321
        self.iface = None
        self.localConfig = localonly_pb2.LocalConfig()
        self.moduleConfig = localonly_pb2.LocalModuleConfig()
        self.channels = []
        self.written = []
        self.owner_updates = []
        self.admin_response = None
        self.admin_responses = []
        self.ack_callback_names = []
        self.session_refreshes = 0
        self.admin_metadata_responses = []
        self.channel_write_responses = []

    def onAckNak(self, _packet):
        pass

    def _respond_to_admin(self):
        response = self.admin_responses.pop(0) if self.admin_responses else self.admin_response
        if response is not None:
            self.ack_callback_names.append(self.onAckNak.__name__)
            self.onAckNak(response)

    def ensureSessionKey(self):
        self.session_refreshes += 1
        self.iface._getOrCreateByNum(to_node_num(self.nodeNum))["adminSessionPassKey"] = b"fresh"

    def writeConfig(self, section):
        self.written.append(section)

    def writeChannel(self, index):
        self.written.append(("write_channel", index))

    def deleteChannel(self, index):
        self.written.append(("delete_channel", index))
        self.channels[index].role = channel_pb2.Channel.Role.DISABLED
        self.channels[index].settings.Clear()

    def setFavorite(self, node_id):
        self.written.append(("favorite", node_id))
        self._respond_to_admin()
        return {"id": 85}

    def removeFavorite(self, node_id):
        self.written.append(("unfavorite", node_id))
        self._respond_to_admin()
        return {"id": 86}

    def setIgnored(self, node_id):
        self.written.append(("ignore", node_id))
        self._respond_to_admin()
        return {"id": 87}

    def removeIgnored(self, node_id):
        self.written.append(("unignore", node_id))
        self._respond_to_admin()
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

    def _sendAdmin(
        self,
        message,
        *,
        wantResponse,
        onResponse,
        adminIndex=0,
    ):
        if message.get_device_metadata_request:
            self.written.append(("metadata", True))
            response = self.admin_metadata_responses.pop(0)
            onResponse(response)
            return {"id": 94}
        if message.get_channel_request:
            index = int(message.get_channel_request) - 1
            response_message = admin_pb2.AdminMessage()
            response_message.get_channel_response.CopyFrom(self.channels[index])
            self.written.append(("read_channel", index))
            onResponse(
                {
                    "decoded": {
                        "portnum": "ADMIN_APP",
                        "admin": {"raw": response_message},
                    }
                }
            )
            return {"id": 95 + index}
        if message.HasField("set_channel"):
            index = int(message.set_channel.index)
            self.written.append(("remote_write_channel", index, adminIndex))
            response = (
                self.channel_write_responses.pop(0)
                if self.channel_write_responses
                else {
                    "decoded": {
                        "portnum": "ROUTING_APP",
                        "routing": {"errorReason": "NONE"},
                    }
                }
            )
            error = (response.get("decoded") or {}).get("routing", {}).get(
                "errorReason"
            )
            if error in {None, "NONE", 0}:
                self.channels[index].CopyFrom(message.set_channel)
            if onResponse:
                onResponse(response)
            return {"id": 110 + index}
        raise AssertionError("Unexpected admin message in test fake")


class FakeInterface:
    def __init__(self) -> None:
        self.localNode = FakeLocalNode()
        self.localNode.iface = self
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
        self.remote_node.iface = self
        self._node_records_by_num = {self.remote_node.nodeNum: {"adminSessionPassKey": b"stale"}}
        self.get_node_requests = []
        self.ack_waits = 0
        self.ack_wait_error = None
        self._acknowledgment = SimpleNamespace(receivedAck=False, receivedNak=False)

    def getMyNodeInfo(self):
        return next(iter(self.nodes.values()))

    def sendText(self, text, **kwargs):
        self.sent.append((text, kwargs))
        return {"id": 42}

    def sendData(self, payload, **kwargs):
        self.sent_data.append((payload, kwargs))
        return {"id": 84}

    def getNode(self, node_id, requestChannels=False, timeout=45):
        self.get_node_requests.append(node_id)
        self.remote_node.nodeNum = node_id
        return self.remote_node

    def _getOrCreateByNum(self, node_num):
        return self._node_records_by_num.setdefault(node_num, {})

    def waitForAckNak(self):
        self.ack_waits += 1
        if self.ack_wait_error:
            raise self.ack_wait_error

    def close(self):
        return None


def connected_manager() -> tuple[MeshtasticManager, FakeInterface]:
    manager = MeshtasticManager()
    interface = FakeInterface()
    manager._interface = interface  # noqa: SLF001 - deliberate unit-test seam
    manager._state = "connected"  # noqa: SLF001
    manager._profile_id = "!87654321"  # noqa: SLF001
    return manager, interface


def test_nodes_are_projected_for_the_ui():
    manager, _ = connected_manager()
    node = manager.nodes()[0]
    assert node["id"] == "!12345678"
    assert node["long_name"] == "Test Node"
    assert node["battery_level"] == 88
    assert node["power_source"] == "battery"
    assert node["hops_away"] == 0
    assert node["via_mqtt"] is False
    assert node["latitude"] == 42.1
    assert node["is_messageable"] is True


def test_external_power_sentinel_is_not_projected_as_101_percent():
    manager, interface = connected_manager()
    interface.nodes["!12345678"]["deviceMetrics"]["batteryLevel"] = 101

    node = manager.nodes()[0]

    assert node["battery_level"] == 101
    assert node["power_source"] == "external"


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
    kwargs["onResponse"]({"decoded": {"requestId": 42, "routing": {"errorReason": "NONE"}}})
    assert manager.events()[0]["kind"] == "outgoing"
    assert manager.events()[1]["kind"] == "delivery"


def test_queued_message_exposes_radio_wait_then_enroute_status():
    manager, interface = connected_manager()
    entered = threading.Event()
    release = threading.Event()

    def blocked_send(text, **kwargs):
        entered.set()
        assert release.wait(2)
        interface.sent.append((text, kwargs))
        return {"id": 43}

    interface.sendText = blocked_send
    queued = manager.queue_text("wait for radio", "!12345678", 0, True)

    assert queued["status"] == "queued"
    assert entered.wait(1)
    assert manager.events()[0]["delivery"] == "queued"
    assert manager.status()["tx_queue"]["active_client_id"] == queued["client_id"]

    release.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if any(event["kind"] == "message_status" for event in manager.events()):
            break
        time.sleep(0.01)

    status_event = next(event for event in manager.events() if event["kind"] == "message_status")
    assert status_event["status"] == "enroute"
    assert status_event["packet_id"] == 43


def test_queued_message_ack_is_correlated_by_client_id():
    manager, interface = connected_manager()
    queued = manager.queue_text("ack me", "!12345678", 0, True)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not interface.sent:
        time.sleep(0.01)
    callback = interface.sent[0][1]["onResponse"]
    callback({"decoded": {"requestId": 42, "routing": {"errorReason": "NONE"}}})

    delivery = next(event for event in manager.events() if event["kind"] == "delivery")
    assert delivery["client_id"] == queued["client_id"]
    assert delivery["status"] == "delivered"


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
    assert (
        MeshtasticManager._classify_connection_error(  # noqa: SLF001
            DeviceIdentityMismatchError("!12345678", "!87654321"),
            "ble",
        )
        == "identity_mismatch"
    )
    assert (
        MeshtasticManager._classify_connection_error(  # noqa: SLF001
            PermissionError("Permission denied: /dev/ttyACM0"),
            "serial",
        )
        == "permission_denied"
    )
    assert (
        MeshtasticManager._classify_connection_error(  # noqa: SLF001
            OSError("No such file or directory: /dev/ttyACM0"),
            "serial",
        )
        == "device_not_found"
    )


def test_serial_connection_uses_common_profile_reconnect_lifecycle(monkeypatch):
    manager = MeshtasticManager()
    captured = {}

    def start_connection(transport, target, **values):
        captured.update(transport=transport, target=target, **values)

    monkeypatch.setattr(manager, "_start_connection", start_connection)
    manager.connect_serial(
        "/dev/serial/by-id/usb-Meshtastic_ABC-if00",
        auto_reconnect=True,
        expected_device_id="!12345678",
    )

    assert captured == {
        "transport": "serial",
        "target": "/dev/serial/by-id/usb-Meshtastic_ABC-if00",
        "auto_reconnect": True,
        "expected_device_id": "!12345678",
        "device": "/dev/serial/by-id/usb-Meshtastic_ABC-if00",
    }

    with pytest.raises(ValueError, match="explicit /dev path"):
        manager.connect_serial("ttyACM0")
    with pytest.raises(ValueError, match="explicit /dev path"):
        manager.connect_serial("/dev/../etc/passwd")


def test_device_metadata_is_projected_as_honest_capability_inventory():
    metadata = mesh_pb2.DeviceMetadata(
        firmware_version="2.7.8",
        device_state_version=22,
        canShutdown=False,
        hasWifi=True,
        hasBluetooth=True,
        hasEthernet=False,
        hasRemoteHardware=False,
        hasPKC=True,
        role=config_pb2.Config.DeviceConfig.Role.CLIENT,
        hw_model=mesh_pb2.HardwareModel.TBEAM,
        excluded_modules=(
            mesh_pb2.ExcludedModules.STOREFORWARD_CONFIG
            | mesh_pb2.ExcludedModules.SERIAL_CONFIG
        ),
    )

    capabilities = MeshtasticManager._project_capabilities(  # noqa: SLF001
        metadata,
        "!12345678",
        "handshake",
    )

    assert capabilities["status"] == "known"
    assert capabilities["firmware_version"] == "2.7.8"
    assert capabilities["hardware_model"] == "TBEAM"
    assert capabilities["role"] == "CLIENT"
    assert capabilities["features"]["wifi"]["state"] == "supported"
    assert capabilities["features"]["shutdown"]["state"] == "unsupported"
    assert capabilities["config_sections"]["store_forward"]["state"] == "unsupported"
    assert capabilities["config_sections"]["serial"]["state"] == "unsupported"
    assert capabilities["config_sections"]["telemetry"]["state"] == "supported"
    assert capabilities["config_sections"]["traffic_management"]["state"] == "unknown"


def test_capability_preflight_blocks_only_explicitly_unsupported_operations():
    manager, interface = connected_manager()
    interface.metadata = mesh_pb2.DeviceMetadata(canShutdown=False, hasPKC=True)

    with pytest.raises(CapabilityUnsupportedError, match="shutdown"):
        manager.request_admin_action("shutdown")

    local = manager._capability_preflight("reboot", None)  # noqa: SLF001
    assert local["state"] == "supported"

    remote_metadata = mesh_pb2.DeviceMetadata(
        hasPKC=False,
        excluded_modules=mesh_pb2.ExcludedModules.NEIGHBORINFO_CONFIG,
    )
    manager._remote_capabilities["!12345678"] = (  # noqa: SLF001
        manager._project_capabilities(  # noqa: SLF001
            remote_metadata,
            "!12345678",
            "remote_admin",
        )
    )
    with pytest.raises(CapabilityUnsupportedError, match="cryptography"):
        manager._capability_preflight(  # noqa: SLF001
            "remote_config",
            "!12345678",
            section="neighbor_info",
        )


def test_unknown_remote_capabilities_are_reported_without_false_blocking():
    manager, _ = connected_manager()

    preflight = manager._capability_preflight(  # noqa: SLF001
        "remote_config",
        "!12345678",
        section="telemetry",
    )

    assert preflight["state"] == "unknown"
    assert "not been loaded" in preflight["reason"]


def test_admin_metadata_response_is_extracted_from_raw_protobuf():
    metadata = mesh_pb2.DeviceMetadata(firmware_version="2.7.8", hasPKC=True)
    raw = admin_pb2.AdminMessage()
    raw.get_device_metadata_response.CopyFrom(metadata)

    extracted = MeshtasticManager._metadata_from_admin_packet(  # noqa: SLF001
        {"decoded": {"admin": {"raw": raw}}}
    )

    assert extracted.firmware_version == "2.7.8"
    assert extracted.hasPKC is True


def test_remote_capability_request_caches_metadata_and_refreshes_stale_session():
    manager, interface = connected_manager()
    metadata = mesh_pb2.DeviceMetadata(
        firmware_version="2.7.8",
        hasPKC=True,
        hw_model=mesh_pb2.HardwareModel.TBEAM,
    )
    raw = admin_pb2.AdminMessage()
    raw.get_device_metadata_response.CopyFrom(metadata)
    interface.remote_node.admin_metadata_responses = [
        {
            "decoded": {
                "routing": {"errorReason": "ADMIN_BAD_SESSION_KEY"},
            }
        },
        {"decoded": {"admin": {"raw": raw}}},
    ]

    accepted = manager.request_capabilities("!12345678")
    deadline = time.monotonic() + 2
    result = None
    while time.monotonic() < deadline:
        result = next(
            (
                event
                for event in manager.events()
                if event["kind"] == "operation_result"
                and event["operation"] == "capabilities"
            ),
            None,
        )
        if result is not None:
            break
        time.sleep(0.01)

    assert accepted == {"status": "requested", "node_id": "!12345678"}
    assert result is not None
    assert result["success"] is True
    assert result["result"]["session_refreshed"] is True
    assert result["result"]["attempts"] == 2
    assert interface.remote_node.session_refreshes == 1
    assert manager.capability_inventory()["remote"]["!12345678"][
        "firmware_version"
    ] == "2.7.8"


def test_remote_capability_rejection_is_cached_as_visible_authorization_result():
    manager, interface = connected_manager()
    interface.remote_node.admin_metadata_responses = [
        {
            "decoded": {
                "routing": {"errorReason": "ADMIN_PUBLIC_KEY_UNAUTHORIZED"},
            }
        }
    ]

    manager.request_capabilities("!12345678")
    deadline = time.monotonic() + 2
    result = None
    while time.monotonic() < deadline:
        result = next(
            (
                event
                for event in manager.events()
                if event["kind"] == "operation_result"
                and event["operation"] == "capabilities"
            ),
            None,
        )
        if result is not None:
            break
        time.sleep(0.01)

    rejected = manager.capability_inventory()["remote"]["!12345678"]
    assert result is not None
    assert result["success"] is False
    assert rejected["status"] == "rejected"
    assert rejected["error_code"] == "ADMIN_PUBLIC_KEY_UNAUTHORIZED"
    preflight = manager._capability_preflight(  # noqa: SLF001
        "remote_config",
        "!12345678",
        section="telemetry",
    )
    assert preflight["state"] == "rejected"


def test_auto_reconnect_waits_with_backoff_and_manual_disconnect_stops_it():
    manager = MeshtasticManager(reconnect_delays=(60,))
    interface = FakeInterface()
    manager._interface = interface  # noqa: SLF001
    manager._state = "connected"  # noqa: SLF001
    manager._transport = "ble"  # noqa: SLF001
    manager._target = "AA:BB:CC:DD:EE:FF"  # noqa: SLF001
    manager._auto_reconnect = True  # noqa: SLF001
    manager._reconnect_transport = "ble"  # noqa: SLF001
    manager._reconnect_target = "AA:BB:CC:DD:EE:FF"  # noqa: SLF001
    manager._reconnect_params = {"address": "AA:BB:CC:DD:EE:FF"}  # noqa: SLF001

    manager._on_connection_lost(interface)  # noqa: SLF001
    waiting = manager.status()
    assert waiting["health"]["state"] == "lost"
    assert waiting["health"]["reconnect"]["phase"] == "waiting"
    assert waiting["health"]["reconnect"]["attempt"] == 1
    assert waiting["health"]["reconnect"]["active"] is True

    manager.disconnect()
    stopped = manager.status()
    assert stopped["state"] == "disconnected"
    assert stopped["health"]["reason"] == "manual"
    assert stopped["health"]["reconnect"]["phase"] == "disabled"


def test_auto_reconnect_timer_starts_a_new_connection_attempt(monkeypatch):
    manager = MeshtasticManager(reconnect_delays=(0.01,))
    interface = FakeInterface()
    attempted = threading.Event()
    manager._interface = interface  # noqa: SLF001
    manager._state = "connected"  # noqa: SLF001
    manager._transport = "tcp"  # noqa: SLF001
    manager._target = "mesh.local:4403"  # noqa: SLF001
    manager._auto_reconnect = True  # noqa: SLF001
    manager._reconnect_transport = "tcp"  # noqa: SLF001
    manager._reconnect_target = "mesh.local:4403"  # noqa: SLF001
    manager._reconnect_params = {"host": "mesh.local", "port": 4403}  # noqa: SLF001

    def fake_connect_worker(*_args):
        attempted.set()

    monkeypatch.setattr(manager, "_connect_worker", fake_connect_worker)
    manager._on_connection_lost(interface)  # noqa: SLF001

    assert attempted.wait(1)
    reconnecting = manager.status()
    assert reconnecting["state"] == "reconnecting"
    assert reconnecting["health"]["reconnect"]["phase"] == "connecting"
    manager.disconnect()


def test_non_transient_failure_blocks_automatic_reconnect():
    manager = MeshtasticManager(reconnect_delays=(0.01,))
    manager._auto_reconnect = True  # noqa: SLF001

    scheduled = manager._schedule_reconnect(  # noqa: SLF001
        manager._generation,  # noqa: SLF001
        "pairing_required",
    )

    assert scheduled is False
    reconnect = manager.status()["health"]["reconnect"]
    assert reconnect["phase"] == "blocked"
    assert reconnect["active"] is False
    manager.disconnect()


def test_stable_reconnect_resets_the_backoff_counter():
    manager = MeshtasticManager(reconnect_stable_seconds=0)
    interface = FakeInterface()
    manager._interface = interface  # noqa: SLF001
    manager._state = "connected"  # noqa: SLF001
    manager._auto_reconnect = True  # noqa: SLF001
    manager._reconnect_attempt = 4  # noqa: SLF001

    manager._mark_reconnect_stable(  # noqa: SLF001
        manager._generation,  # noqa: SLF001
        interface,
    )

    reconnect = manager.status()["health"]["reconnect"]
    assert reconnect["attempt"] == 0
    assert reconnect["phase"] == "armed"
    manager.disconnect()


def test_ble_disconnect_callback_hands_loss_to_manager_without_blocking():
    class FakeBleakBackend:
        callback = None

        def set_disconnected_callback(self, callback):
            self.callback = callback

    class FakeBleakClient:
        def __init__(self):
            self._backend = FakeBleakBackend()
            self.is_connected = True

    manager = MeshtasticManager(ble_health_poll_seconds=60)
    interface = FakeInterface()
    interface.client = type("Client", (), {"bleak_client": FakeBleakClient()})()
    manager._interface = interface  # noqa: SLF001
    manager._state = "connected"  # noqa: SLF001
    manager._transport = "ble"  # noqa: SLF001
    manager._target = "AA:BB:CC:DD:EE:FF"  # noqa: SLF001

    manager._start_ble_transport_monitor(  # noqa: SLF001
        manager._generation,  # noqa: SLF001
        interface,
    )
    callback = interface.client.bleak_client._backend.callback
    assert callback is not None

    callback()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and manager.status()["state"] == "connected":
        time.sleep(0.01)

    assert manager.status()["health"]["reason"] == "connection_lost"


def test_ble_watchdog_detects_disconnect_when_library_callback_is_missing():
    class FakeBleakClient:
        is_connected = False
        _backend = object()

    manager = MeshtasticManager(ble_health_poll_seconds=0.01)
    interface = FakeInterface()
    interface.client = type("Client", (), {"bleak_client": FakeBleakClient()})()
    manager._interface = interface  # noqa: SLF001
    manager._state = "connected"  # noqa: SLF001
    manager._transport = "ble"  # noqa: SLF001
    manager._target = "AA:BB:CC:DD:EE:FF"  # noqa: SLF001

    manager._start_ble_transport_monitor(  # noqa: SLF001
        manager._generation,  # noqa: SLF001
        interface,
    )
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and manager.status()["state"] == "connected":
        time.sleep(0.01)

    assert manager.status()["health"]["state"] == "lost"
    assert manager.status()["health"]["reason"] == "connection_lost"


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


def test_traceroute_cooldown_is_global_but_does_not_block_telemetry():
    manager, interface = connected_manager()
    manager.request_node_action("!12345678", "traceroute")

    try:
        manager.request_node_action("!abcdef01", "traceroute")
    except RequestCooldownError as exc:
        assert exc.action == "traceroute"
        assert exc.scope == "global"
        assert exc.remaining_seconds > 0
    else:
        raise AssertionError("Expected a global traceroute cooldown")

    manager.request_node_action("!abcdef01", "telemetry")
    active = manager.status()["request_controls"]["active"]
    assert active[0]["action"] == "traceroute"
    assert active[0]["target"] is None
    assert len(interface.sent_data) == 2


def test_neighbor_info_cooldown_is_per_node_and_user_info_is_available():
    manager, interface = connected_manager()
    manager.request_node_action("!12345678", "neighbor_info")
    manager.request_node_action("!abcdef01", "neighbor_info")
    manager.request_node_action("!abcdef01", "user_info")

    try:
        manager.request_node_action("!12345678", "neighbor_info")
    except RequestCooldownError as exc:
        assert exc.scope == "node"
    else:
        raise AssertionError("Expected a per-node Neighbor Info cooldown")

    ports = [kwargs["portNum"] for _, kwargs in interface.sent_data]
    assert portnums_pb2.PortNum.NEIGHBORINFO_APP in ports
    assert portnums_pb2.PortNum.NODEINFO_APP in ports


def test_neighbor_info_result_keeps_neighbors_but_removes_duplicate_raw_projection():
    manager, interface = connected_manager()
    manager.request_node_action("!12345678", "neighbor_info")
    _, kwargs = interface.sent_data[0]
    raw = mesh_pb2.NeighborInfo(
        node_id=0x12345678,
        last_sent_by_id=0x12345678,
        node_broadcast_interval_secs=21600,
        neighbors=[
            mesh_pb2.Neighbor(
                node_id=0x87654321,
                snr=7.25,
                last_rx_time=1_700_000_000,
                node_broadcast_interval_secs=900,
            )
        ],
    )
    kwargs["onResponse"](
        {
            "decoded": {
                "portnum": "NEIGHBORINFO_APP",
                "neighborinfo": {
                    "nodeId": 0x12345678,
                    "lastSentById": 0x12345678,
                    "nodeBroadcastIntervalSecs": 21600,
                    "neighbors": [
                        {
                            "nodeId": 0x87654321,
                            "snr": 7.25,
                            "lastRxTime": "1700000000",
                            "nodeBroadcastIntervalSecs": 900,
                        }
                    ],
                    "raw": raw,
                },
            }
        }
    )

    result = manager.events()[-1]["result"]["neighbor_info"]
    assert "raw" not in result
    assert result["neighbors"][0]["snr"] == 7.25
    assert result["nodeBroadcastIntervalSecs"] == 21600


def test_node_management_action_updates_local_nodedb():
    manager, interface = connected_manager()
    packet = manager.request_node_action("!12345678", "favorite")
    assert packet == {"id": 85}
    assert interface.localNode.written == [("favorite", "!12345678")]
    assert manager.nodes()[0]["is_favorite"] is True

    manager.request_node_action("!12345678", "unfavorite")
    assert manager.nodes()[0]["is_favorite"] is False
    manager.request_node_action("!12345678", "ignore")
    assert manager.nodes()[0]["is_ignored"] is True
    manager.request_node_action("!12345678", "unignore")
    assert manager.nodes()[0]["is_ignored"] is False
    assert manager.events()[0]["operation"] == "favorite"


def test_managed_radio_is_not_exposed_as_its_own_preference_target():
    manager, interface = connected_manager()
    interface.nodes["!87654321"] = {
        "num": 0x87654321,
        "user": {
            "id": "!87654321",
            "longName": "Gateway",
            "shortName": "GATE",
        },
        "isFavorite": True,
        "isIgnored": True,
    }

    self_node = next(node for node in manager.nodes() if node["id"] == "!87654321")
    assert self_node["is_self"] is True
    assert self_node["is_favorite"] is False
    assert self_node["is_ignored"] is False

    try:
        manager.request_node_action("!87654321", "favorite")
    except ValueError as exc:
        assert "managed radio itself" in str(exc)
    else:
        raise AssertionError("Expected a self-preference operation to be rejected")


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
                "position_precision_label": "0 bits · не споделя позиция",
                "encrypted": True,
        }
    ]


def test_channel_manager_lists_all_slots_without_exposing_psk():
    manager, interface = connected_manager()
    primary = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    primary.settings.name = "Main"
    primary.settings.psk = b"\x01"
    disabled = channel_pb2.Channel(index=1, role=channel_pb2.Channel.Role.DISABLED)
    later = channel_pb2.Channel(index=2, role=channel_pb2.Channel.Role.DISABLED)
    interface.localNode.channels = [primary, disabled, later]

    slots = manager.channel_slots()
    assert len(slots) == 3
    assert slots[0]["psk_state"] == "default"
    assert "psk" not in slots[0]
    assert slots[1]["editable"] is True
    assert slots[2]["editable"] is False


def test_position_precision_has_operator_facing_summaries():
    assert MeshtasticManager._position_precision_summary(0) == (  # noqa: SLF001
        "0 bits · не споделя позиция"
    )
    assert MeshtasticManager._position_precision_summary(16) == (  # noqa: SLF001
        "16 bits · ≈ 364 m"
    )
    assert "GPS" in MeshtasticManager._position_precision_summary(32)  # noqa: SLF001


def test_channel_psk_is_revealed_only_by_explicit_method_without_audit_event():
    manager, interface = connected_manager()
    primary = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    primary.settings.name = "Main"
    primary.settings.psk = b"\x01"
    interface.localNode.channels = [primary]
    event_count = len(manager.events())

    revealed = manager.channel_psk(0)

    assert revealed == {
        "index": 0,
        "psk_base64": "AQ==",
        "psk_state": "default",
        "byte_length": 1,
        "publicly_known": True,
        "encrypted": True,
    }
    assert len(manager.events()) == event_count
    assert "psk_base64" not in manager.channel_slots()[0]


def test_channel_admin_response_with_psk_is_not_added_to_generic_history():
    manager, interface = connected_manager()
    channel = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    channel.settings.psk = bytes(range(32))
    admin = admin_pb2.AdminMessage()
    admin.get_channel_response.CopyFrom(channel)
    event_count = len(manager.events())

    manager._on_receive(  # noqa: SLF001 - verify secret filtering at pubsub boundary
        {
            "fromId": "!12345678",
            "decoded": {
                "portnum": "ADMIN_APP",
                "admin": {"raw": admin},
            },
        },
        interface,
    )

    assert len(manager.events()) == event_count


def test_channel_manager_adds_updates_and_disables_secondary_channel(tmp_path):
    manager, interface = connected_manager()
    manager._history = EncryptedHistory(tmp_path / "logs", key=b"c" * 32)  # noqa: SLF001
    primary = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    primary.settings.name = "Main"
    primary.settings.psk = bytes(range(16))
    disabled = channel_pb2.Channel(index=1, role=channel_pb2.Channel.Role.DISABLED)
    interface.localNode.channels = [primary, disabled]

    values = (1, "SECONDARY", "Ops", "random", "", True, False, 12)
    preview = manager.preview_channel(*values)
    precision_change = next(
        item for item in preview["changes"] if item["field"] == "position_precision"
    )
    assert precision_change["before"] == "0 bits · не споделя позиция"
    assert precision_change["after"] == "12 bits · ≈ 5.8 km"
    result = manager.update_channel(
        *values,
        preview_token=preview["preview_token"],
    )
    secondary = interface.localNode.channels[1]
    assert secondary.Role.Name(secondary.role) == "SECONDARY"
    assert secondary.settings.name == "Ops"
    assert len(secondary.settings.psk) == 32
    assert secondary.settings.uplink_enabled is True
    assert secondary.settings.module_settings.position_precision == 12
    assert interface.localNode.written[-1] == ("write_channel", 1)
    assert result["channels"][1]["enabled"] is True
    assert result["backup"]["encrypted"] is True
    backups = manager._history.load_private(  # noqa: SLF001
        "!87654321",
        "channel-backups",
    )
    assert backups[-1]["target_channel"] == 1
    assert len(backups[-1]["channels"]) == 2
    saved_primary = channel_pb2.Channel()
    saved_primary.ParseFromString(
        base64.b64decode(backups[-1]["channels"][0]["protobuf_base64"])
    )
    assert saved_primary.settings.psk == bytes(range(16))
    saved_secondary = channel_pb2.Channel()
    saved_secondary.ParseFromString(
        base64.b64decode(backups[-1]["channels"][1]["protobuf_base64"])
    )
    assert saved_secondary.Role.Name(saved_secondary.role) == "DISABLED"
    ciphertext = (tmp_path / "logs" / "!87654321.channel-backups.aes").read_bytes()
    assert b"protobuf_base64" not in ciphertext

    disable_values = (1, "DISABLED", "Ops", "unchanged", "", False, False, 0)
    disable_preview = manager.preview_channel(*disable_values)
    manager.update_channel(
        *disable_values,
        preview_token=disable_preview["preview_token"],
    )
    assert interface.localNode.written[-1] == ("delete_channel", 1)
    assert manager.channel_slots()[1]["enabled"] is False


def test_channel_manager_accepts_simple_marker_and_custom_aes128(tmp_path):
    manager, interface = connected_manager()
    manager._history = EncryptedHistory(tmp_path / "logs", key=b"c" * 32)  # noqa: SLF001
    primary = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    primary.settings.name = "Main"
    interface.localNode.channels = [primary]

    simple_values = (0, "PRIMARY", "Main", "custom", "simple15", False, False, 0)
    simple_preview = manager.preview_channel(*simple_values)
    manager.update_channel(
        *simple_values,
        preview_token=simple_preview["preview_token"],
    )
    assert interface.localNode.channels[0].settings.psk == b"\x10"
    assert manager.channel_slots()[0]["psk_state"] == "simple15"

    aes_values = (
        0,
        "PRIMARY",
        "Main",
        "custom",
        "base64:AAECAwQFBgcICQoLDA0ODw==",
        False,
        False,
        0,
    )
    aes_preview = manager.preview_channel(*aes_values)
    manager.update_channel(
        *aes_values,
        preview_token=aes_preview["preview_token"],
    )
    assert interface.localNode.channels[0].settings.psk == bytes(range(16))


def test_channel_preview_hides_psk_and_rejects_changed_radio_state():
    manager, interface = connected_manager()
    primary = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    primary.settings.name = "Main"
    interface.localNode.channels = [primary]
    values = (
        0,
        "PRIMARY",
        "Private",
        "custom",
        "base64:AAECAwQFBgcICQoLDA0ODw==",
        False,
        False,
        0,
    )

    preview = manager.preview_channel(*values)

    assert preview["has_changes"] is True
    assert "AAECAwQFBgcICQoLDA0ODw" not in json.dumps(preview)
    psk_change = next(item for item in preview["changes"] if item["field"] == "psk")
    assert psk_change["after"] == "secret AES-128"
    primary.settings.name = "Changed elsewhere"
    with pytest.raises(ValueError, match="state changed after preview"):
        manager.update_channel(*values, preview_token=preview["preview_token"])


def test_channel_preview_detects_same_size_secret_replacement():
    manager, interface = connected_manager()
    primary = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    primary.settings.name = "Main"
    primary.settings.psk = bytes(range(16))
    interface.localNode.channels = [primary]

    preview = manager.preview_channel(
        0,
        "PRIMARY",
        "Main",
        "custom",
        "base64:EBESExQVFhcYGRobHB0eHw==",
        False,
        False,
        0,
    )

    assert preview["has_changes"] is True
    assert preview["changes"] == [
        {
            "field": "psk",
            "label": "PSK",
            "before": "secret AES-128",
            "after": "secret AES-128 (нов ключ)",
            "severity": "sensitive",
        }
    ]


def test_channel_write_requires_matching_one_time_preview(tmp_path):
    manager, interface = connected_manager()
    manager._history = EncryptedHistory(tmp_path / "logs", key=b"c" * 32)  # noqa: SLF001
    primary = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    primary.settings.name = "Main"
    interface.localNode.channels = [primary]
    values = (0, "PRIMARY", "NewName", "unchanged", "", False, False, 0)

    with pytest.raises(ValueError, match="preview is required"):
        manager.update_channel(*values)
    preview = manager.preview_channel(*values)
    with pytest.raises(ValueError, match="request changed after preview"):
        manager.update_channel(
            0,
            "PRIMARY",
            "Different",
            "unchanged",
            "",
            False,
            False,
            0,
            preview_token=preview["preview_token"],
        )
    with pytest.raises(ValueError, match="preview expired"):
        manager.update_channel(*values, preview_token=preview["preview_token"])


def test_channel_backup_is_persisted_before_failed_radio_write(tmp_path):
    manager, interface = connected_manager()
    history = EncryptedHistory(tmp_path / "logs", key=b"c" * 32)
    manager._history = history  # noqa: SLF001
    primary = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    primary.settings.name = "Main"
    primary.settings.psk = bytes(range(16))
    interface.localNode.channels = [primary]
    values = (0, "PRIMARY", "NewName", "unchanged", "", False, False, 0)
    preview = manager.preview_channel(*values)

    def fail_write(_index):
        raise RuntimeError("radio write failed")

    interface.localNode.writeChannel = fail_write
    with pytest.raises(RuntimeError, match="radio write failed"):
        manager.update_channel(*values, preview_token=preview["preview_token"])

    backups = history.load_private("!87654321", "channel-backups")
    assert len(backups) == 1
    assert backups[0]["operation"] == "update"
    assert primary.settings.name == "Main"


def test_remote_channel_manager_loads_writes_and_verifies_target_snapshot(tmp_path):
    manager, interface = connected_manager()
    manager._history = EncryptedHistory(tmp_path / "logs", key=b"r" * 32)  # noqa: SLF001
    remote_channels = []
    for index in range(8):
        role = (
            channel_pb2.Channel.Role.PRIMARY
            if index == 0
            else channel_pb2.Channel.Role.DISABLED
        )
        channel = channel_pb2.Channel(index=index, role=role)
        if index == 0:
            channel.settings.name = "Remote"
            channel.settings.psk = b"\x01"
        remote_channels.append(channel)
    interface.remote_node.channels = remote_channels

    requested = manager.request_remote_channels("!12345678")
    assert requested == {"status": "requested", "node_id": "!12345678"}
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        events = manager.events()
        if any(
            event.get("operation") == "remote_channels"
            and event.get("kind") == "operation_result"
            for event in events
        ):
            break
        time.sleep(0.01)

    result_event = next(
        event
        for event in manager.events()
        if event.get("operation") == "remote_channels"
        and event.get("kind") == "operation_result"
    )
    assert result_event["success"] is True
    assert result_event["result"]["channel_count"] == 8
    assert manager.channel_slots("!12345678")[0]["display_name"] == "Remote"

    values = (1, "SECONDARY", "Ops", "random", "", False, False, 16)
    preview = manager.preview_channel(*values, node_id="!12345678")
    assert preview["remote"] is True
    assert preview["node_id"] == "!12345678"
    applied = manager.update_channel(
        *values,
        preview_token=preview["preview_token"],
        node_id="!12345678",
    )

    assert applied["remote"] is True
    assert applied["verification"]["verified"] is True
    assert interface.remote_node.channels[1].settings.name == "Ops"
    assert ("remote_write_channel", 1, 0) in interface.remote_node.written
    remote_psk = base64.b64encode(
        bytes(interface.remote_node.channels[1].settings.psk)
    ).decode("ascii")
    assert remote_psk not in json.dumps(manager.events())
    backups = manager._history.load_private(  # noqa: SLF001
        "!12345678",
        "channel-backups",
    )
    assert backups[-1]["remote"] is True
    assert backups[-1]["managed_via"] == "!87654321"


def test_channel_preview_token_is_bound_to_managed_target(tmp_path):
    manager, interface = connected_manager()
    manager._history = EncryptedHistory(tmp_path / "logs", key=b"r" * 32)  # noqa: SLF001
    local = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    local.settings.name = "Local"
    remote = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    remote.settings.name = "Remote"
    interface.localNode.channels = [local]
    interface.remote_node.channels = [remote]
    manager._remote_nodes["!12345678"] = interface.remote_node  # noqa: SLF001
    manager._remote_channels_loaded.add("!12345678")  # noqa: SLF001

    values = (0, "PRIMARY", "Changed", "unchanged", "", False, False, 0)
    preview = manager.preview_channel(*values, node_id="!12345678")

    with pytest.raises(ValueError, match="request changed after preview"):
        manager.update_channel(
            *values,
            preview_token=preview["preview_token"],
        )


def test_remote_channel_write_refreshes_bad_admin_session_once(tmp_path):
    manager, interface = connected_manager()
    manager._history = EncryptedHistory(tmp_path / "logs", key=b"r" * 32)  # noqa: SLF001
    remote = channel_pb2.Channel(index=0, role=channel_pb2.Channel.Role.PRIMARY)
    remote.settings.name = "Remote"
    interface.remote_node.nodeNum = 0x12345678
    interface.remote_node.channels = [remote]
    interface.remote_node.channel_write_responses = [
        {
            "decoded": {
                "portnum": "ROUTING_APP",
                "routing": {"errorReason": "ADMIN_BAD_SESSION_KEY"},
            }
        },
        {
            "decoded": {
                "portnum": "ROUTING_APP",
                "routing": {"errorReason": "NONE"},
            }
        },
    ]
    manager._remote_nodes["!12345678"] = interface.remote_node  # noqa: SLF001
    manager._remote_channels_loaded.add("!12345678")  # noqa: SLF001
    values = (0, "PRIMARY", "Changed", "unchanged", "", False, False, 0)
    preview = manager.preview_channel(*values, node_id="!12345678")

    result = manager.update_channel(
        *values,
        preview_token=preview["preview_token"],
        node_id="!12345678",
    )

    assert result["session_refreshed"] is True
    assert result["verification"]["verified"] is True
    assert interface.remote_node.session_refreshes >= 3
    assert [
        item for item in interface.remote_node.written if item[0] == "remote_write_channel"
    ] == [
        ("remote_write_channel", 0, 0),
        ("remote_write_channel", 0, 0),
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


def test_every_config_field_has_type_default_domain_and_recommendation_metadata():
    manager, _ = connected_manager()
    sections = manager.config()["sections"]

    for section in sections:
        for field in section["fields"]:
            metadata = field["metadata"]
            assert metadata["protocol_type"], f"missing type for {section['name']}.{field['name']}"
            assert (
                metadata.get("default") is not None or metadata.get("protocol_default") is not None
            )
            assert metadata["domain"], f"missing domain for {section['name']}.{field['name']}"
            assert metadata["recommended"], (
                f"missing recommendation for {section['name']}.{field['name']}"
            )


def test_config_metadata_exposes_firmware_limits_and_friendly_protocol_choices():
    manager, _ = connected_manager()
    sections = manager.config()["sections"]
    neighbor = next(item for item in sections if item["name"] == "neighbor_info")
    interval = next(item for item in neighbor["fields"] if item["name"] == "update_interval")
    assert interval["metadata"]["minimum"] == 14400
    assert interval["metadata"]["default"] == "21600 s · 6 часа"

    network = next(item for item in sections if item["name"] == "network")
    protocols = next(item for item in network["fields"] if item["name"] == "enabled_protocols")
    assert protocols["label"] == "Допълнително IP излъчване"
    assert [item["value"] for item in protocols["metadata"]["choices"]] == [0, 1]

    position = next(item for item in sections if item["name"] == "position")
    flags = next(item for item in position["fields"] if item["name"] == "position_flags")
    assert flags["metadata"]["value_format"] == "bitmask"
    assert flags["metadata"]["maximum"] == 1023
    assert {item["label"] for item in flags["metadata"]["flags"]} >= {
        "Altitude",
        "GPS timestamp",
        "Speed",
    }

    bluetooth = next(item for item in sections if item["name"] == "bluetooth")
    fixed_pin = next(item for item in bluetooth["fields"] if item["name"] == "fixed_pin")
    assert fixed_pin["metadata"]["minimum"] == 100000
    assert fixed_pin["metadata"]["maximum"] == 999999

    lora = next(item for item in sections if item["name"] == "lora")
    spread_factor = next(item for item in lora["fields"] if item["name"] == "spread_factor")
    assert [item["value"] for item in spread_factor["metadata"]["choices"]] == [
        0,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
    ]


def test_config_sections_are_annotated_and_excluded_module_writes_are_blocked():
    manager, interface = connected_manager()
    interface.metadata = mesh_pb2.DeviceMetadata(
        hasPKC=True,
        excluded_modules=mesh_pb2.ExcludedModules.NEIGHBORINFO_CONFIG,
    )

    sections = manager.config()["sections"]
    neighbor = next(item for item in sections if item["name"] == "neighbor_info")
    telemetry = next(item for item in sections if item["name"] == "telemetry")

    assert neighbor["capability"]["state"] == "unsupported"
    assert telemetry["capability"]["state"] == "supported"
    with pytest.raises(CapabilityUnsupportedError, match="NEIGHBORINFO_CONFIG"):
        manager.update_config("neighbor_info", {"enabled": True})


def test_neighbor_interval_below_firmware_minimum_is_rejected():
    manager, _ = connected_manager()

    try:
        manager.update_config("neighbor_info", {"update_interval": 3600})
    except ValueError as exc:
        assert "at least 14400" in str(exc)
    else:
        raise AssertionError("Expected Neighbor Info firmware range validation")


def test_custom_lora_discrete_values_are_validated():
    manager, _ = connected_manager()

    with pytest.raises(ValueError, match="spread_factor must be one of"):
        manager.update_config("lora", {"spread_factor": 4})


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
    result = manager.events()[-1]
    assert result["result"]["state_verified"] is False
    assert result["result"]["remote_state_readable"] is False


def test_remote_nodedb_preference_distinguishes_ack_and_nak():
    manager, interface = connected_manager()
    interface.remote_node.admin_response = {
        "from": 0x87654321,
        "decoded": {
            "portnum": "ROUTING_APP",
            "routing": {"errorReason": "NONE"},
        },
    }

    manager.request_node_action(
        "!12345678",
        "favorite",
        managed_node_id="!87654321",
    )
    ack = manager.events()[-1]
    assert ack["success"] is True
    assert ack["result"]["acknowledgment"] == "ack"
    assert interface.remote_node.ack_callback_names == ["onAckNak"]
    assert "onAckNak" not in interface.remote_node.__dict__

    interface.remote_node.admin_response = {
        "from": 0x87654321,
        "decoded": {
            "portnum": "ROUTING_APP",
            "routing": {"errorReason": "NOT_AUTHORIZED"},
        },
    }
    try:
        manager.request_node_action(
            "!12345678",
            "unfavorite",
            managed_node_id="!87654321",
        )
    except RuntimeError as exc:
        assert "NOT_AUTHORIZED" in str(exc)
    else:
        raise AssertionError("Expected remote NAK to reject the operation")
    nak = manager.events()[-1]
    assert nak["success"] is False
    assert nak["error"] == "NOT_AUTHORIZED"
    assert nak["result"]["acknowledgment"] == "nak"


def test_remote_nodedb_preference_refreshes_a_bad_admin_session_once():
    manager, interface = connected_manager()
    interface.remote_node.admin_responses = [
        {
            "from": 0x87654321,
            "decoded": {
                "portnum": "ROUTING_APP",
                "routing": {"errorReason": "ADMIN_BAD_SESSION_KEY"},
            },
        },
        {
            "from": 0x87654321,
            "decoded": {
                "portnum": "ROUTING_APP",
                "routing": {"errorReason": "NONE"},
            },
        },
    ]

    manager.request_node_action(
        "!12345678",
        "favorite",
        managed_node_id="!87654321",
    )

    assert interface.remote_node.written == [
        ("favorite", "!12345678"),
        ("favorite", "!12345678"),
    ]
    assert interface.get_node_requests == [0x87654321]
    assert interface.remote_node.session_refreshes == 1
    assert interface._getOrCreateByNum(0x87654321)["adminSessionPassKey"] == b"fresh"
    result = manager.events()[-1]
    assert result["success"] is True
    assert result["result"]["acknowledgment"] == "ack"
    assert result["result"]["session_refreshed"] is True
    assert result["result"]["attempts"] == 2


def test_remote_nodedb_preference_records_ack_timeout():
    manager, interface = connected_manager()
    interface.ack_wait_error = RuntimeError("Timed out waiting for an acknowledgment")

    try:
        manager.request_node_action(
            "!12345678",
            "ignore",
            managed_node_id="!87654321",
        )
    except RuntimeError as exc:
        assert "Timed out" in str(exc)
    else:
        raise AssertionError("Expected remote ACK timeout")
    result = manager.events()[-1]
    assert result["success"] is False
    assert result["result"]["acknowledgment"] == "timeout"


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
