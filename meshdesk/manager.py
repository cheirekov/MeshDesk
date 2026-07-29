from __future__ import annotations

import contextlib
import logging
import re
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.message import Message
from meshtastic.protobuf import (
    mesh_pb2,
    portnums_pb2,
    storeforward_pb2,
    telemetry_pb2,
)
from pubsub import pub

from meshdesk.history import EncryptedHistory
from meshdesk.pairing import BluetoothPairer

logger = logging.getLogger(__name__)

LOCAL_CONFIGS = {
    "device": "Device",
    "position": "Position / GPS",
    "power": "Power",
    "network": "Network / Wi-Fi",
    "display": "Display",
    "lora": "LoRa radio",
    "bluetooth": "Bluetooth",
    "security": "Security",
}
MODULE_CONFIGS = {
    "mqtt": "MQTT",
    "serial": "Serial",
    "external_notification": "External notification",
    "store_forward": "Store & forward",
    "range_test": "Range test",
    "telemetry": "Telemetry",
    "canned_message": "Canned message",
    "audio": "Audio",
    "remote_hardware": "Remote hardware",
    "neighbor_info": "Neighbor info",
    "detection_sensor": "Detection sensor",
    "ambient_lighting": "Ambient lighting",
    "paxcounter": "PAX counter",
    "traffic_management": "Traffic management",
}
SECRET_FIELDS = {"wifi_psk", "password", "private_key", "fixed_pin"}
INTERFACE_CLOSE_TIMEOUT = 6
TELEMETRY_TYPES = {
    "device": "device_metrics",
    "environment": "environment_metrics",
    "air_quality": "air_quality_metrics",
    "power": "power_metrics",
    "local_stats": "local_stats",
}
HISTORY_EVENT_KINDS = {
    "incoming",
    "outgoing",
    "delivery",
    "operation_request",
    "operation_result",
    "store_forward",
}
OWNER_SECTION = "owner"
DEFAULT_HISTORY_WINDOW_MINUTES = 60 * 24
DEFAULT_HISTORY_MAX_MESSAGES = 100


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe(value: Any) -> Any:
    """Convert Meshtastic/protobuf values into JSON-compatible values."""
    if isinstance(value, Message):
        return MessageToDict(value, preserving_proto_field_name=True)
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _pick(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return default


class MeshtasticManager:
    """Own one radio connection and expose a thread-safe UI-facing state."""

    def __init__(
        self,
        event_limit: int = 500,
        history: EncryptedHistory | None = None,
        history_directory: Path | str = "logs",
    ) -> None:
        self._lock = threading.RLock()
        self._command_lock = threading.Lock()
        self._interface: Any | None = None
        self._generation = 0
        self._state = "disconnected"
        self._transport: str | None = None
        self._target: str | None = None
        self._error: str | None = None
        self._connected_at: str | None = None
        self._events: deque[dict[str, Any]] = deque(maxlen=event_limit)
        self._sequence = 0
        self._profile_id: str | None = None
        self._profile_name: str | None = None
        self._history = history
        self._history_directory = Path(history_directory)
        self._remote_nodes: dict[str, Any] = {}
        self._remote_loaded_sections: dict[str, set[str]] = {}
        self._history_replay_requested_at: int | None = None
        self._history_replay_remaining = 0
        self._pending_receive_packets: list[tuple[Any, dict[str, Any]]] = []
        self.pairer = BluetoothPairer()

        pub.subscribe(self._on_receive, "meshtastic.receive")
        pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")

    def _add_event(self, kind: str, **data: Any) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            event = {
                "event_id": uuid.uuid4().hex,
                "seq": self._sequence,
                "time": _now(),
                "kind": kind,
                "profile_id": self._profile_id,
                **_safe(data),
            }
            self._events.append(event)
            profile_id = self._profile_id
        if profile_id and kind in HISTORY_EVENT_KINDS:
            try:
                self._history_store().append(profile_id, event)
            except Exception:
                logger.exception("Unable to persist encrypted MeshDesk history")
        return event

    def _history_store(self) -> EncryptedHistory:
        with self._lock:
            if self._history is None:
                self._history = EncryptedHistory(self._history_directory)
            return self._history

    @staticmethod
    def _interface_profile(interface: Any) -> tuple[str, str]:
        info = _safe(interface.getMyNodeInfo()) or {}
        user = info.get("user") or {}
        node_id = user.get("id")
        if not node_id:
            number = info.get("num") or getattr(interface.localNode, "nodeNum", 0)
            node_id = f"!{int(number):08x}"
        name = user.get("longName") or user.get("long_name") or node_id
        return str(node_id).lower(), str(name)

    def connect_tcp(self, host: str, port: int = 4403) -> None:
        host = host.strip()
        if not host:
            raise ValueError("TCP host is required")
        if not 1 <= port <= 65535:
            raise ValueError("TCP port must be between 1 and 65535")
        self._start_connection("tcp", f"{host}:{port}", host=host, port=port)

    def connect_ble(self, address: str) -> None:
        address = address.strip()
        if not address:
            raise ValueError("Choose a Bluetooth device first")
        self._start_connection("ble", address, address=address)

    def _start_connection(self, transport: str, target: str, **params: Any) -> None:
        self.disconnect()
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._state = "connecting"
            self._transport = transport
            self._target = target
            self._error = None
            self._connected_at = None
            self._profile_id = None
            self._profile_name = None
            self._remote_nodes = {}
            self._remote_loaded_sections = {}
            self._history_replay_requested_at = None
            self._history_replay_remaining = 0
            self._pending_receive_packets = []
        self._add_event("status", message=f"Connecting via {transport.upper()} to {target}")
        threading.Thread(
            target=self._connect_worker,
            args=(generation, transport, params),
            name=f"meshdesk-connect-{transport}",
            daemon=True,
        ).start()

    def _connect_worker(self, generation: int, transport: str, params: dict[str, Any]) -> None:
        interface = None
        try:
            if transport == "tcp":
                from meshtastic.tcp_interface import TCPInterface

                interface = TCPInterface(
                    hostname=params["host"],
                    portNumber=params["port"],
                    timeout=45,
                )
            else:
                from meshtastic.ble_interface import BLEInterface

                for attempt in range(1, 4):
                    self.pairer.disconnect_device(params["address"])
                    time.sleep(1.5)
                    try:
                        interface = BLEInterface(address=params["address"], timeout=45)
                        break
                    except BLEInterface.BLEError as exc:
                        error_kind = getattr(exc, "kind", None)
                        device_not_found_kind = getattr(
                            BLEInterface.BLEError,
                            "DEVICE_NOT_FOUND",
                            "device_not_found",
                        )
                        can_retry = (
                            (
                                error_kind == device_not_found_kind
                                or "No Meshtastic BLE peripheral" in str(exc)
                            )
                            and attempt < 3
                        )
                        if not can_retry:
                            raise
                        self._add_event(
                            "status",
                            message=(
                                "Radio is paired but not advertising yet; "
                                f"BLE retry {attempt + 1}/3"
                            ),
                        )
                        time.sleep(2)
            profile_id, profile_name = self._interface_profile(interface)
            with self._lock:
                if generation != self._generation:
                    stale = True
                else:
                    stale = False
                    self._interface = interface
                    self._state = "connected"
                    self._error = None
                    self._connected_at = _now()
                    self._profile_id = profile_id
                    self._profile_name = profile_name
                    pending_packets = [
                        packet
                        for pending_interface, packet in self._pending_receive_packets
                        if pending_interface is interface
                    ]
                    self._pending_receive_packets = []
            if stale:
                interface.close()
                return
            self._add_event("status", message="Connected and node database loaded")
            for pending_packet in pending_packets:
                self._on_receive(pending_packet, interface)
            threading.Thread(
                target=self._history_replay_after_connect,
                args=(generation, interface),
                name="meshdesk-history-replay",
                daemon=True,
            ).start()
        except Exception as exc:  # Hardware/network errors vary by platform.
            logger.exception("Meshtastic connection failed")
            if interface is not None:
                with contextlib.suppress(Exception):
                    interface.close()
            with self._lock:
                if generation != self._generation:
                    return
                self._interface = None
                self._state = "error"
                self._error = str(exc) or type(exc).__name__
            self._add_event("error", message=self._error)

    def disconnect(self) -> None:
        with self._lock:
            self._generation += 1
            interface = self._interface
            transport = self._transport
            target = self._target
            had_connection = interface is not None or self._state in {"connecting", "connected"}
            self._interface = None
            self._state = "disconnected"
            self._transport = None
            self._target = None
            self._error = None
            self._connected_at = None
        if interface is not None:
            close_finished = threading.Event()

            def close_interface() -> None:
                try:
                    interface.close()
                except Exception:
                    logger.exception("Error while closing Meshtastic interface")
                finally:
                    close_finished.set()

            threading.Thread(
                target=close_interface,
                name="meshdesk-interface-close",
                daemon=True,
            ).start()
            if not close_finished.wait(timeout=INTERFACE_CLOSE_TIMEOUT):
                logger.warning("Meshtastic interface close timed out; forcing transport release")
        if transport == "ble" and target:
            self.pairer.disconnect_device(target)
        if had_connection:
            self._add_event("status", message="Disconnected")

    @staticmethod
    def scan_ble() -> list[dict[str, Any]]:
        from meshtastic.ble_interface import BLEInterface

        return [
            {"name": device.name or "Meshtastic", "address": device.address}
            for device in BLEInterface.scan()
        ]

    def channels(self) -> list[dict[str, Any]]:
        with self._lock:
            interface = self._interface
            if interface is None:
                return []
            raw_channels = list(interface.localNode.channels or [])

        result = []
        for channel in raw_channels:
            role = channel.Role.Name(channel.role)
            if role == "DISABLED":
                continue
            settings = channel.settings
            result.append(
                {
                    "index": channel.index,
                    "name": settings.name
                    or ("Primary" if channel.index == 0 else f"Channel {channel.index}"),
                    "role": role,
                    "uplink_enabled": settings.uplink_enabled,
                    "downlink_enabled": settings.downlink_enabled,
                    "position_precision": settings.module_settings.position_precision,
                    "encrypted": bool(settings.psk),
                }
            )
        return result

    def send_text(
        self,
        text: str,
        destination: str = "^all",
        channel: int = 0,
        want_ack: bool = True,
    ) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("Message cannot be empty")
        if len(text.encode("utf-8")) > 230:
            raise ValueError("Message is too long (maximum 230 UTF-8 bytes)")
        if not 0 <= channel <= 7:
            raise ValueError("Channel must be between 0 and 7")

        with self._lock:
            interface = self._interface
            if self._state != "connected" or interface is None:
                raise RuntimeError("Not connected to a Meshtastic device")

        destination = destination.strip() or "^all"
        if destination != "^all" and not re.fullmatch(r"![0-9a-fA-F]{8}", destination):
            raise ValueError("Direct destination must be a node ID such as !1234abcd")

        response_holder: dict[str, Any] = {"packet_id": None}

        def onAckNak(response: dict[str, Any]) -> None:  # Name is significant to meshtastic-python.
            decoded = response.get("decoded") or {}
            routing = decoded.get("routing") or {}
            error = routing.get("errorReason", "NONE")
            self._add_event(
                "delivery",
                packet_id=response_holder["packet_id"] or decoded.get("requestId"),
                status="delivered" if error == "NONE" else "failed",
                error=error,
                to=destination,
            )

        with self._command_lock:
            packet = interface.sendText(
                text,
                destinationId=destination,
                channelIndex=channel,
                wantAck=want_ack,
                onResponse=onAckNak if want_ack else None,
            )
        safe_packet = _safe(packet)
        response_holder["packet_id"] = safe_packet.get("id")
        self._add_event(
            "outgoing",
            text=text,
            to=destination or "^all",
            channel=channel,
            want_ack=want_ack,
            packet=safe_packet,
        )
        return safe_packet

    @staticmethod
    def _validate_node_destination(node_id: str) -> str:
        node_id = node_id.strip()
        if not re.fullmatch(r"![0-9a-fA-F]{8}", node_id):
            raise ValueError("Destination must be a node ID such as !1234abcd")
        return node_id

    def _connected_interface(self) -> Any:
        with self._lock:
            interface = self._interface
            if self._state != "connected" or interface is None:
                raise RuntimeError("Not connected to a Meshtastic device")
            return interface

    def _managed_node(self, node_id: str | None = None) -> Any:
        interface = self._connected_interface()
        if not node_id:
            return interface.localNode
        node_id = self._validate_node_destination(node_id).lower()
        with self._lock:
            remote = self._remote_nodes.get(node_id)
        if remote is None:
            remote = interface.getNode(node_id, requestChannels=False, timeout=45)
            with self._lock:
                if interface is self._interface:
                    self._remote_nodes[node_id] = remote
        return remote

    @staticmethod
    def _operation_error(packet: dict[str, Any]) -> str | None:
        decoded = packet.get("decoded") or {}
        if decoded.get("portnum") != "ROUTING_APP":
            return None
        routing = decoded.get("routing") or {}
        reason = routing.get("errorReason") or routing.get("error_reason")
        return None if reason in {None, "NONE"} else reason

    @staticmethod
    def _route_nodes(
        node_numbers: list[int],
        snr_values: list[int],
    ) -> list[dict[str, Any]]:
        result = []
        snr_valid = len(snr_values) == len(node_numbers)
        for index, number in enumerate(node_numbers):
            encoded_snr = snr_values[index] if snr_valid else -128
            result.append(
                {
                    "num": number,
                    "id": f"!{number:08x}",
                    "snr": None if encoded_snr == -128 else encoded_snr / 4,
                }
            )
        return result

    def _record_operation_response(
        self,
        operation: str,
        target: str,
        telemetry_type: str | None,
        response_holder: dict[str, Any],
        packet: dict[str, Any],
    ) -> None:
        error = self._operation_error(packet)
        decoded = packet.get("decoded") or {}
        result: dict[str, Any] = {}
        if operation == "traceroute" and not error:
            trace = decoded.get("traceroute") or {}
            route = trace.get("route") or []
            route_back = trace.get("routeBack") or trace.get("route_back") or []
            snr_towards = trace.get("snrTowards") or trace.get("snr_towards") or []
            snr_back = trace.get("snrBack") or trace.get("snr_back") or []
            local_num = packet.get("to")
            remote_num = packet.get("from")
            towards_numbers = [
                number
                for number in [local_num, *route, remote_num]
                if isinstance(number, int)
            ]
            back_numbers = [
                number
                for number in [remote_num, *route_back, local_num]
                if isinstance(number, int)
            ] if packet.get("hopStart") is not None and len(snr_back) == len(route_back) + 1 else []
            result = {
                "route_towards": self._route_nodes(
                    towards_numbers,
                    [-128, *list(snr_towards)],
                ),
                "route_back": self._route_nodes(
                    back_numbers,
                    [-128, *list(snr_back)],
                ),
            }
        elif operation == "telemetry" and not error:
            result = {"telemetry": decoded.get("telemetry") or {}}
        elif operation == "position" and not error:
            result = {"position": decoded.get("position") or {}}

        self._add_event(
            "operation_result",
            operation=operation,
            target=target,
            telemetry_type=telemetry_type,
            request_packet_id=response_holder.get("packet_id"),
            success=error is None,
            error=error,
            result=result,
            packet=packet,
        )

    def request_node_action(
        self,
        node_id: str,
        action: str,
        channel: int = 0,
        telemetry_type: str = "device",
        hop_limit: int | None = None,
        managed_node_id: str | None = None,
    ) -> dict[str, Any]:
        node_id = self._validate_node_destination(node_id)
        if not 0 <= channel <= 7:
            raise ValueError("Channel must be between 0 and 7")
        if hop_limit is not None and not 1 <= hop_limit <= 7:
            raise ValueError("Hop limit must be between 1 and 7")
        supported_actions = {
            "traceroute",
            "telemetry",
            "position",
            "favorite",
            "unfavorite",
            "ignore",
            "unignore",
        }
        if action not in supported_actions:
            raise ValueError(f"Unsupported node action: {action}")
        if telemetry_type not in TELEMETRY_TYPES:
            raise ValueError(f"Unsupported telemetry type: {telemetry_type}")

        interface = self._connected_interface()
        management_methods = {
            "favorite": "setFavorite",
            "unfavorite": "removeFavorite",
            "ignore": "setIgnored",
            "unignore": "removeIgnored",
        }
        if action in management_methods:
            managed_node_id = (
                self._validate_node_destination(managed_node_id).lower()
                if managed_node_id
                else None
            )
            managed_node = self._managed_node(managed_node_id)
            with self._command_lock:
                packet = getattr(managed_node, management_methods[action])(node_id)
                if managed_node_id:
                    interface.waitForAckNak()
            safe_packet = _safe(packet)
            self._add_event(
                "operation_result",
                operation=action,
                target=node_id,
                managed_node=managed_node_id or self._profile_id,
                remote=bool(managed_node_id),
                success=True,
                result={"updated": True},
                packet=safe_packet,
            )
            return safe_packet

        if hop_limit is None:
            hop_limit = int(interface.localNode.localConfig.lora.hop_limit or 3)

        response_holder: dict[str, Any] = {"packet_id": None}

        def on_response(packet: dict[str, Any]) -> None:
            self._record_operation_response(
                action,
                node_id,
                telemetry_type if action == "telemetry" else None,
                response_holder,
                packet,
            )

        if action == "traceroute":
            payload: Message = mesh_pb2.RouteDiscovery()
            portnum = portnums_pb2.PortNum.TRACEROUTE_APP
        elif action == "position":
            payload = mesh_pb2.Position()
            portnum = portnums_pb2.PortNum.POSITION_APP
        else:
            payload = telemetry_pb2.Telemetry()
            field_name = TELEMETRY_TYPES[telemetry_type]
            getattr(payload, field_name).SetInParent()
            portnum = portnums_pb2.PortNum.TELEMETRY_APP

        with self._command_lock:
            packet = interface.sendData(
                payload,
                destinationId=node_id,
                portNum=portnum,
                wantResponse=True,
                onResponse=on_response,
                channelIndex=channel,
                hopLimit=hop_limit,
            )
        safe_packet = _safe(packet)
        response_holder["packet_id"] = safe_packet.get("id")
        self._add_event(
            "operation_request",
            operation=action,
            target=node_id,
            telemetry_type=telemetry_type if action == "telemetry" else None,
            channel=channel,
            hop_limit=hop_limit,
            packet=safe_packet,
        )
        return safe_packet

    def _owner_values(self, node_id: str | None = None) -> dict[str, Any]:
        interface = self._connected_interface()
        if node_id:
            target = self._validate_node_destination(node_id).lower()
            records = list((interface.nodes or {}).values())
            record = next(
                (
                    _safe(item)
                    for item in records
                    if str((_safe(item).get("user") or {}).get("id", "")).lower()
                    == target
                ),
                {},
            )
        else:
            record = _safe(interface.getMyNodeInfo()) or {}
        user = record.get("user") or {}
        return {
            "long_name": _pick(user, "longName", "long_name", default=""),
            "short_name": _pick(user, "shortName", "short_name", default=""),
            "is_licensed": bool(
                _pick(user, "isLicensed", "is_licensed", default=False)
            ),
            "is_unmessagable": bool(
                _pick(
                    user,
                    "isUnmessagable",
                    "is_unmessagable",
                    default=False,
                )
            ),
        }

    def _owner_section(self, node_id: str | None = None) -> dict[str, Any]:
        values = self._owner_values(node_id)
        definitions = [
            ("long_name", "Дълго име", "string"),
            ("short_name", "Кратко име (до 4 знака)", "string"),
            ("is_licensed", "Лицензиран радиолюбител", "bool"),
            (
                "is_unmessagable",
                "Да не приема лични съобщения",
                "bool",
            ),
        ]
        return {
            "name": OWNER_SECTION,
            "label": "Потребител / име",
            "kind": "owner",
            "fields": [
                {
                    "name": name,
                    "label": label,
                    "type": field_type,
                    "value": values[name],
                    "enum_values": [],
                    "repeated": False,
                    "secret": False,
                    "read_only": False,
                }
                for name, label, field_type in definitions
            ],
        }

    def _config_sections(
        self,
        local_node: Any,
        only: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        sections = []
        for section, label in {**LOCAL_CONFIGS, **MODULE_CONFIGS}.items():
            if only is not None and section not in only:
                continue
            root = local_node.localConfig if section in LOCAL_CONFIGS else local_node.moduleConfig
            message = getattr(root, section)
            fields = []
            for descriptor in message.DESCRIPTOR.fields:
                if descriptor.GetOptions().deprecated or descriptor.message_type is not None:
                    continue
                is_bytes = descriptor.type == descriptor.TYPE_BYTES
                secret = descriptor.name in SECRET_FIELDS
                value = getattr(message, descriptor.name)
                if is_bytes:
                    value = ""
                elif descriptor.is_repeated:
                    value = list(value)
                elif descriptor.enum_type is not None:
                    enum_number = int(value)
                    enum_descriptor = descriptor.enum_type.values_by_number.get(enum_number)
                    value = (
                        enum_descriptor.name
                        if enum_descriptor is not None
                        else f"UNKNOWN ({enum_number})"
                    )
                elif secret:
                    value = ""
                fields.append(
                    {
                        "name": descriptor.name,
                        "label": descriptor.name.replace("_", " ").title(),
                        "type": (
                            "enum"
                            if descriptor.enum_type is not None
                            else "bool"
                            if descriptor.type == descriptor.TYPE_BOOL
                            else "float"
                            if descriptor.type in {descriptor.TYPE_FLOAT, descriptor.TYPE_DOUBLE}
                            else "string"
                            if descriptor.type in {descriptor.TYPE_STRING, descriptor.TYPE_BYTES}
                            else "integer"
                        ),
                        "value": value,
                        "enum_values": (
                            (
                                [value]
                                if descriptor.enum_type is not None
                                and isinstance(value, str)
                                and value.startswith("UNKNOWN (")
                                else []
                            )
                            + [item.name for item in descriptor.enum_type.values]
                            if descriptor.enum_type is not None
                            else []
                        ),
                        "repeated": descriptor.is_repeated,
                        "secret": secret,
                        "read_only": is_bytes,
                    }
                )
            if fields:
                sections.append(
                    {
                        "name": section,
                        "label": label,
                        "kind": "radio" if section in LOCAL_CONFIGS else "module",
                        "fields": fields,
                    }
                )
        return sections

    def config(self, node_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            interface = self._interface
            if interface is None:
                return {"sections": [], "node_id": node_id, "remote": bool(node_id)}
            if node_id:
                node_id = self._validate_node_destination(node_id).lower()
                local_node = self._remote_nodes.get(node_id)
                loaded = self._remote_loaded_sections.get(node_id, set()).copy()
            else:
                local_node = interface.localNode
                loaded = None
        sections = [self._owner_section(node_id)]
        if local_node is not None:
            sections.extend(self._config_sections(local_node, loaded))
        return {
            "sections": sections,
            "node_id": node_id or self._profile_id,
            "remote": bool(node_id),
        }

    def update_config(
        self,
        section: str,
        values: dict[str, Any],
        node_id: str | None = None,
    ) -> None:
        if (
            section != OWNER_SECTION
            and section not in LOCAL_CONFIGS
            and section not in MODULE_CONFIGS
        ):
            raise ValueError("Unknown configuration section")
        if section == OWNER_SECTION:
            self._update_owner(values, node_id)
            return
        with self._lock:
            interface = self._interface
            if self._state != "connected" or interface is None:
                raise RuntimeError("Not connected to a Meshtastic device")
            if node_id:
                node_id = self._validate_node_destination(node_id).lower()
                local_node = self._remote_nodes.get(node_id)
                if local_node is None or section not in self._remote_loaded_sections.get(
                    node_id, set()
                ):
                    raise RuntimeError("Load this remote configuration section before editing")
            else:
                local_node = interface.localNode
            root = local_node.localConfig if section in LOCAL_CONFIGS else local_node.moduleConfig
            target = getattr(root, section)

        allowed = {
            field.name: field
            for field in target.DESCRIPTOR.fields
            if not field.GetOptions().deprecated and field.message_type is None
        }
        unknown = set(values) - set(allowed)
        if unknown:
            raise ValueError(f"Unsupported fields: {', '.join(sorted(unknown))}")

        patch = {}
        for name, value in values.items():
            field = allowed[name]
            if field.type == field.TYPE_BYTES:
                raise ValueError(f"{name} is read-only")
            if name in SECRET_FIELDS and value == "":
                continue
            if field.is_repeated and isinstance(value, str):
                value = [part.strip() for part in value.split(",") if part.strip()]
            patch[name] = value

        candidate = type(target)()
        candidate.CopyFrom(target)
        try:
            ParseDict(patch, candidate, ignore_unknown_fields=False)
        except Exception as exc:
            raise ValueError(f"Invalid configuration value: {exc}") from exc

        with self._command_lock:
            target.CopyFrom(candidate)
            local_node.writeConfig(section)
            if node_id:
                interface.waitForAckNak()
        self._add_event(
            "config",
            message=f"Configuration section '{section}' written",
            node_id=node_id or self._profile_id,
            remote=bool(node_id),
        )

    def _update_owner(
        self,
        values: dict[str, Any],
        node_id: str | None = None,
    ) -> None:
        allowed = {
            "long_name",
            "short_name",
            "is_licensed",
            "is_unmessagable",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unsupported owner fields: {', '.join(sorted(unknown))}")
        current = self._owner_values(node_id)
        current.update(values)
        long_name = str(current["long_name"]).strip()
        short_name = str(current["short_name"]).strip()
        if not long_name:
            raise ValueError("Дългото име не може да бъде празно")
        if not short_name:
            raise ValueError("Краткото име не може да бъде празно")
        if len(short_name) > 4:
            raise ValueError("Краткото име може да съдържа най-много 4 знака")
        managed = self._managed_node(node_id)
        interface = self._connected_interface()
        with self._command_lock:
            managed.setOwner(
                long_name=long_name,
                short_name=short_name,
                is_licensed=bool(current["is_licensed"]),
                is_unmessagable=bool(current["is_unmessagable"]),
            )
            if node_id:
                interface.waitForAckNak()
        self._add_event(
            "config",
            message="Owner/User settings written",
            node_id=node_id or self._profile_id,
            remote=bool(node_id),
        )

    def request_remote_config(self, node_id: str, section: str) -> None:
        node_id = self._validate_node_destination(node_id).lower()
        if section not in LOCAL_CONFIGS and section not in MODULE_CONFIGS:
            raise ValueError("Unknown configuration section")
        interface = self._connected_interface()
        with self._lock:
            generation = self._generation
        self._add_event(
            "operation_request",
            operation="remote_config",
            target=node_id,
            section=section,
        )

        def worker() -> None:
            try:
                with self._command_lock:
                    with self._lock:
                        remote = self._remote_nodes.get(node_id)
                    if remote is None:
                        remote = interface.getNode(
                            node_id,
                            requestChannels=False,
                            timeout=45,
                        )
                    root = (
                        remote.localConfig
                        if section in LOCAL_CONFIGS
                        else remote.moduleConfig
                    )
                    descriptor = root.DESCRIPTOR.fields_by_name[section]
                    remote.requestConfig(descriptor)
                with self._lock:
                    if generation != self._generation or interface is not self._interface:
                        return
                    self._remote_nodes[node_id] = remote
                    self._remote_loaded_sections.setdefault(node_id, set()).add(section)
                result = self._config_sections(remote, {section})[0]
                self._add_event(
                    "operation_result",
                    operation="remote_config",
                    target=node_id,
                    section=section,
                    success=True,
                    result={"config_section": result},
                )
            except Exception as exc:
                logger.exception("Remote configuration request failed")
                self._add_event(
                    "operation_result",
                    operation="remote_config",
                    target=node_id,
                    section=section,
                    success=False,
                    error=str(exc) or type(exc).__name__,
                )

        threading.Thread(
            target=worker,
            name=f"meshdesk-remote-config-{node_id}-{section}",
            daemon=True,
        ).start()

    def export_config(self, node_id: str | None = None) -> dict[str, Any]:
        config = self.config(node_id)
        sections = {}
        for section in config["sections"]:
            values = {
                field["name"]: field["value"]
                for field in section["fields"]
                if not field["secret"]
                and not field["read_only"]
                and not (
                    field["type"] == "enum"
                    and isinstance(field["value"], str)
                    and field["value"].startswith("UNKNOWN (")
                )
            }
            sections[section["name"]] = values
        if not sections:
            raise RuntimeError("No configuration sections are loaded for export")
        return {
            "format": "meshdesk-config-v1",
            "exported_at": _now(),
            "node_id": config.get("node_id"),
            "remote": config.get("remote", False),
            "sections": sections,
        }

    def import_config(
        self,
        document: dict[str, Any],
        node_id: str | None = None,
    ) -> dict[str, Any]:
        if document.get("format") != "meshdesk-config-v1":
            raise ValueError("Unsupported MeshDesk configuration export")
        sections = document.get("sections")
        if not isinstance(sections, dict) or not sections:
            raise ValueError("The configuration export has no sections")
        written = []
        for section, values in sections.items():
            if not isinstance(values, dict):
                raise ValueError(f"Invalid values for configuration section '{section}'")
            self.update_config(section, values, node_id)
            written.append(section)
        self._add_event(
            "config",
            message=f"Imported {len(written)} configuration sections",
            node_id=node_id or self._profile_id,
            remote=bool(node_id),
        )
        return {"written": written}

    def request_admin_action(
        self,
        action: str,
        node_id: str | None = None,
        preserve_node_preferences: bool = False,
    ) -> None:
        supported = {
            "reboot",
            "shutdown",
            "reset_nodedb",
            "factory_reset_config",
            "factory_reset_device",
        }
        if action not in supported:
            raise ValueError(f"Unsupported administration action: {action}")
        node_id = (
            self._validate_node_destination(node_id).lower() if node_id else None
        )
        if preserve_node_preferences and (
            action != "reset_nodedb" or node_id is not None
        ):
            raise ValueError(
                "Favorite/ignored preservation is available only when resetting "
                "the connected radio's NodeDB"
            )
        interface = self._connected_interface()
        with self._lock:
            generation = self._generation
        self._add_event(
            "operation_request",
            operation="administration",
            admin_action=action,
            target=node_id or self._profile_id,
            remote=bool(node_id),
            preserve_node_preferences=preserve_node_preferences,
        )

        def worker() -> None:
            preferences: list[tuple[str, str]] = []
            try:
                if action == "reset_nodedb" and preserve_node_preferences:
                    for record in list((interface.nodes or {}).values()):
                        item = _safe(record)
                        user = item.get("user") or {}
                        target = user.get("id")
                        if not target:
                            continue
                        if _pick(item, "isFavorite", "is_favorite", default=False):
                            preferences.append(("setFavorite", target))
                        if _pick(item, "isIgnored", "is_ignored", default=False):
                            preferences.append(("setIgnored", target))

                managed = self._managed_node(node_id)
                with self._command_lock:
                    if action == "reboot":
                        packet = managed.reboot(secs=10)
                    elif action == "shutdown":
                        packet = managed.shutdown(secs=10)
                    elif action == "factory_reset_config":
                        packet = managed.factoryReset(full=False)
                    elif action == "factory_reset_device":
                        packet = managed.factoryReset(full=True)
                    else:
                        packet = managed.resetNodeDb()
                    if node_id:
                        interface.waitForAckNak()

                restored = 0
                if preferences:
                    time.sleep(2)
                    with self._lock:
                        still_current = (
                            generation == self._generation
                            and interface is self._interface
                        )
                    if still_current:
                        with self._command_lock:
                            for method, target in preferences:
                                getattr(interface.localNode, method)(target)
                                restored += 1

                self._add_event(
                    "operation_result",
                    operation="administration",
                    admin_action=action,
                    target=node_id or self._profile_id,
                    remote=bool(node_id),
                    success=True,
                    result={
                        "accepted": True,
                        "restored_preferences": restored,
                    },
                    packet=_safe(packet),
                )
            except Exception as exc:
                logger.exception("Meshtastic administration action failed")
                self._add_event(
                    "operation_result",
                    operation="administration",
                    admin_action=action,
                    target=node_id or self._profile_id,
                    remote=bool(node_id),
                    success=False,
                    error=str(exc) or type(exc).__name__,
                )

        threading.Thread(
            target=worker,
            name=f"meshdesk-admin-{action}",
            daemon=True,
        ).start()

    def _last_history_marker(self) -> int:
        with self._lock:
            profile_id = self._profile_id
        if not profile_id:
            return 0
        with contextlib.suppress(Exception):
            for event in reversed(self._history_store().load(profile_id)):
                if (
                    event.get("kind") == "store_forward"
                    and event.get("status") == "history"
                ):
                    marker = event.get("last_request")
                    if isinstance(marker, int) and marker > 0:
                        return marker
        return 0

    def request_history_replay(
        self,
        window_minutes: int | None = None,
        max_messages: int | None = None,
        *,
        automatic: bool = False,
    ) -> dict[str, Any]:
        interface = self._connected_interface()
        with self._lock:
            profile_id = self._profile_id
        if not profile_id:
            raise RuntimeError("The connected radio profile is not ready")

        config = interface.localNode.moduleConfig.store_forward
        window = int(
            window_minutes
            if window_minutes is not None
            else config.history_return_window or DEFAULT_HISTORY_WINDOW_MINUTES
        )
        maximum = int(
            max_messages
            if max_messages is not None
            else config.history_return_max or DEFAULT_HISTORY_MAX_MESSAGES
        )
        if not 1 <= window <= 60 * 24 * 30:
            raise ValueError("History window must be between 1 and 43200 minutes")
        if not 1 <= maximum <= 500:
            raise ValueError("History maximum must be between 1 and 500 messages")
        last_request = self._last_history_marker()
        payload = storeforward_pb2.StoreAndForward(
            rr=storeforward_pb2.StoreAndForward.CLIENT_HISTORY,
            history=storeforward_pb2.StoreAndForward.History(
                last_request=last_request,
                window=window,
                history_messages=maximum,
            ),
        )
        with self._command_lock:
            packet = interface.sendData(
                payload,
                destinationId=profile_id,
                portNum=portnums_pb2.PortNum.STORE_FORWARD_APP,
                wantAck=False,
                channelIndex=0,
            )
        with self._lock:
            self._history_replay_requested_at = int(time.time())
            self._history_replay_remaining = 0
        safe_packet = _safe(packet)
        self._add_event(
            "operation_request",
            operation="history_replay",
            target=profile_id,
            automatic=automatic,
            last_request=last_request,
            window=window,
            max_messages=maximum,
            packet=safe_packet,
        )
        return safe_packet

    def _history_replay_after_connect(self, generation: int, interface: Any) -> None:
        time.sleep(0.75)
        with self._lock:
            if generation != self._generation or interface is not self._interface:
                return
        try:
            self.request_history_replay(automatic=True)
        except Exception as exc:
            logger.info("Automatic history replay was not available: %s", exc)
            self._add_event(
                "operation_result",
                operation="history_replay",
                target=self._profile_id,
                automatic=True,
                success=False,
                error=str(exc) or type(exc).__name__,
            )

    def status(self) -> dict[str, Any]:
        with self._lock:
            interface = self._interface
            result = {
                "state": self._state,
                "transport": self._transport,
                "target": self._target,
                "error": self._error,
                "connected_at": self._connected_at,
                "event_sequence": self._sequence,
                "profile_id": self._profile_id,
                "profile_name": self._profile_name,
            }
        if interface is not None:
            with contextlib.suppress(Exception):
                result["my_node"] = _safe(interface.getMyNodeInfo())
            with contextlib.suppress(Exception):
                result["public_key"] = _safe(interface.getPublicKey())
        return result

    def nodes(self) -> list[dict[str, Any]]:
        with self._lock:
            interface = self._interface
            if interface is None:
                return []
            raw_nodes = list((interface.nodes or {}).values())

        nodes: list[dict[str, Any]] = []
        for raw in raw_nodes:
            node = _safe(raw)
            user = node.get("user") or {}
            metrics = node.get("deviceMetrics") or node.get("device_metrics") or {}
            position = node.get("position") or {}
            nodes.append(
                {
                    "num": node.get("num"),
                    "id": user.get("id") or f"!{node.get('num', 0):08x}",
                    "long_name": user.get("longName") or user.get("long_name") or "Unknown",
                    "short_name": user.get("shortName") or user.get("short_name") or "?",
                    "hardware": user.get("hwModel") or user.get("hw_model"),
                    "role": user.get("role"),
                    "is_messageable": not (
                        user.get("isUnmessagable") or user.get("is_unmessagable")
                    ),
                    "is_favorite": _pick(node, "isFavorite", "is_favorite", default=False),
                    "is_ignored": _pick(node, "isIgnored", "is_ignored", default=False),
                    "is_muted": _pick(node, "isMuted", "is_muted", default=False),
                    "channel": node.get("channel"),
                    "via_mqtt": _pick(node, "viaMqtt", "via_mqtt", default=False),
                    "last_heard": _pick(node, "lastHeard", "last_heard"),
                    "snr": node.get("snr"),
                    "hops_away": _pick(node, "hopsAway", "hops_away"),
                    "battery_level": _pick(metrics, "batteryLevel", "battery_level"),
                    "voltage": metrics.get("voltage"),
                    "latitude": _pick(
                        position,
                        "latitude",
                        default=position.get("latitude_i", 0) / 1e7,
                    ),
                    "longitude": _pick(
                        position,
                        "longitude",
                        default=position.get("longitude_i", 0) / 1e7,
                    ),
                    "altitude": position.get("altitude"),
                    "position": position,
                    "device_metrics": metrics,
                    "environment_metrics": node.get("environmentMetrics")
                    or node.get("environment_metrics")
                    or {},
                    "air_quality_metrics": node.get("airQualityMetrics")
                    or node.get("air_quality_metrics")
                    or {},
                    "power_metrics": node.get("powerMetrics")
                    or node.get("power_metrics")
                    or {},
                    "local_stats": node.get("localStats") or node.get("local_stats") or {},
                    "raw": node,
                }
            )
        return sorted(nodes, key=lambda item: (item["long_name"].lower(), item["id"]))

    def events(self, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return [event.copy() for event in self._events if event["seq"] > after]

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            profile_id = self._profile_id
        if not profile_id:
            return []
        return self._history_store().load(profile_id)

    def _handle_store_forward(
        self,
        packet: dict[str, Any],
        decoded: dict[str, Any],
    ) -> bool:
        store_forward = decoded.get("storeforward") or decoded.get("storeForward")
        if not isinstance(store_forward, dict):
            return False
        raw = store_forward.get("raw")
        rr_value = store_forward.get("rr", "")
        if raw is not None:
            with contextlib.suppress(Exception):
                rr_value = storeforward_pb2.StoreAndForward.RequestResponse.Name(
                    raw.rr
                )
        rr = str(rr_value)

        if rr in {"ROUTER_TEXT_DIRECT", "ROUTER_TEXT_BROADCAST"}:
            text_value: Any = store_forward.get("text", "")
            if raw is not None:
                with contextlib.suppress(Exception):
                    text_value = bytes(raw.text)
            if isinstance(text_value, bytes):
                text = text_value.decode("utf-8", errors="replace")
            else:
                text = str(text_value)
            direct = rr == "ROUTER_TEXT_DIRECT"
            from_id = packet.get("fromId") or packet.get("from")
            self._add_event(
                "incoming",
                text=text,
                portnum="TEXT_MESSAGE_APP",
                original_portnum="STORE_FORWARD_APP",
                store_forward=True,
                recovered=True,
                is_direct=direct,
                conversation=(
                    f"direct:{from_id}"
                    if direct
                    else f"channel:{packet.get('channel', 0)}"
                ),
                **{
                    "from": from_id,
                    "to": packet.get("toId") or packet.get("to"),
                    "channel": packet.get("channel", 0),
                    "snr": packet.get("rxSnr"),
                    "rssi": packet.get("rxRssi"),
                    "via_mqtt": packet.get("viaMqtt") or False,
                    "packet": packet,
                },
            )
            return True

        history = store_forward.get("history")
        if raw is not None:
            with contextlib.suppress(Exception):
                if raw.HasField("history"):
                    history = {
                        "historyMessages": raw.history.history_messages,
                        "window": raw.history.window,
                        "lastRequest": raw.history.last_request,
                    }
        if isinstance(history, dict):
            history_messages = int(
                _pick(history, "historyMessages", "history_messages", default=0)
            )
            with self._lock:
                self._history_replay_remaining = history_messages
            self._add_event(
                "store_forward",
                status="history",
                router=packet.get("fromId") or packet.get("from"),
                history_messages=history_messages,
                window=int(history.get("window", 0)),
                last_request=int(
                    _pick(history, "lastRequest", "last_request", default=0)
                ),
                packet=packet,
            )
            return True

        stats = store_forward.get("stats")
        if raw is not None:
            with contextlib.suppress(Exception):
                if raw.HasField("stats"):
                    stats = MessageToDict(
                        raw.stats,
                        preserving_proto_field_name=True,
                    )
        if isinstance(stats, dict):
            self._add_event(
                "store_forward",
                status="stats",
                router=packet.get("fromId") or packet.get("from"),
                stats=stats,
                packet=packet,
            )
            return True

        self._add_event(
            "store_forward",
            status=rr or "response",
            router=packet.get("fromId") or packet.get("from"),
            packet=packet,
        )
        return True

    def _on_receive(self, packet: dict[str, Any], interface: Any) -> None:
        with self._lock:
            if interface is not self._interface:
                if self._state == "connecting" and self._interface is None:
                    self._pending_receive_packets.append((interface, packet))
                return
        decoded = packet.get("decoded") or {}
        if decoded.get("portnum") == "STORE_FORWARD_APP" and self._handle_store_forward(
            packet, decoded
        ):
            return
        recovered = False
        if decoded.get("portnum") == "TEXT_MESSAGE_APP":
            rx_time = _pick(packet, "rxTime", "rx_time")
            with self._lock:
                if (
                    self._history_replay_remaining > 0
                    and self._history_replay_requested_at is not None
                    and isinstance(rx_time, (int, float))
                    and int(rx_time) <= self._history_replay_requested_at
                ):
                    recovered = True
                    self._history_replay_remaining -= 1
        to_id = packet.get("toId")
        is_direct = bool(to_id and to_id != "^all")
        hop_start = packet.get("hopStart")
        hop_limit = packet.get("hopLimit")
        hops_travelled = (
            hop_start - hop_limit
            if isinstance(hop_start, int) and isinstance(hop_limit, int)
            else None
        )
        self._add_event(
            "incoming",
            text=decoded.get("text"),
            portnum=decoded.get("portnum"),
            store_forward=recovered,
            recovered=recovered,
            is_direct=is_direct,
            conversation=(
                f"direct:{packet.get('fromId') or packet.get('from')}"
                if is_direct
                else f"channel:{packet.get('channel', 0)}"
            ),
            **{
                "from": packet.get("fromId") or packet.get("from"),
                "to": packet.get("toId") or packet.get("to"),
                "channel": packet.get("channel"),
                "snr": packet.get("rxSnr"),
                "rssi": packet.get("rxRssi"),
                "hop_limit": packet.get("hopLimit"),
                "hop_start": packet.get("hopStart"),
                "hops_travelled": hops_travelled,
                "via_mqtt": packet.get("viaMqtt") or False,
                "relay_node": packet.get("relayNode"),
                "next_hop": packet.get("nextHop"),
                "transport_mechanism": packet.get("transportMechanism"),
                "request_id": decoded.get("requestId"),
                "reply_id": decoded.get("replyId"),
                "packet": packet,
            },
        )

    def _on_connection_lost(self, interface: Any) -> None:
        with self._lock:
            if interface is not self._interface:
                return
            self._interface = None
            self._state = "error"
            self._error = "Connection to the Meshtastic device was lost"
        self._add_event("error", message=self._error)

    def wait_until_settled(self, timeout: float = 10.0) -> str:
        """Small helper used by integration tests and diagnostics."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.status()["state"]
            if state != "connecting":
                return state
            time.sleep(0.05)
        return self.status()["state"]
