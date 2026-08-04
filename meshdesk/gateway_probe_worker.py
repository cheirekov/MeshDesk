from __future__ import annotations

import base64
import json
import logging
import socket
import sys
import time
from datetime import UTC, datetime
from typing import Any

from meshtastic.tcp_interface import TCPInterface

from meshdesk.gateway_diagnostics import channel_signature


class BoundedTCPInterface(TCPInterface):
    def __init__(self, *args: Any, connect_timeout: float = 4.0, **kwargs: Any) -> None:
        self._diagnostic_connect_timeout = connect_timeout
        super().__init__(*args, **kwargs)

    def myConnect(self) -> None:
        sock = socket.create_connection(
            (self.hostname, self.portNumber),
            timeout=self._diagnostic_connect_timeout,
        )
        sock.settimeout(None)
        self.socket = sock


def _enum_name(message: Any, field_name: str) -> str | None:
    field = message.DESCRIPTOR.fields_by_name.get(field_name)
    if field is None or field.enum_type is None:
        return None
    value = int(getattr(message, field_name))
    descriptor = field.enum_type.values_by_number.get(value)
    return descriptor.name if descriptor else f"UNKNOWN ({value})"


def _timestamp(value: Any) -> str | None:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, UTC).isoformat()


def _probe(request: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    interface = BoundedTCPInterface(
        hostname=str(request["host"]),
        portNumber=int(request.get("port") or 4403),
        timeout=10,
        connect_timeout=4,
    )
    try:
        info = interface.getMyNodeInfo() or {}
        user = info.get("user") or {}
        node_id = str(user.get("id") or "").lower()
        lora = interface.localNode.localConfig.lora
        network = interface.localNode.localConfig.network
        mqtt = interface.localNode.moduleConfig.mqtt
        nonce = base64.b64decode(request["nonce"], validate=True)
        channels = []
        for channel in list(interface.localNode.channels or []):
            role_name = channel.Role.Name(channel.role)
            settings = channel.settings
            channels.append(
                {
                    "index": int(channel.index),
                    "role": role_name,
                    "enabled": role_name != "DISABLED",
                    "name": settings.name,
                    "uplink_enabled": bool(settings.uplink_enabled),
                    "downlink_enabled": bool(settings.downlink_enabled),
                    "signature": channel_signature(
                        nonce,
                        int(channel.index),
                        int(channel.role),
                        settings.name,
                        bytes(settings.psk),
                    ),
                }
            )
        subject_id = str(request["subject_node_id"]).lower()
        subject = interface.nodes.get(subject_id) or {}
        metadata = getattr(interface, "metadata", None)
        observation = None
        if subject:
            observation = {
                "last_heard": _timestamp(subject.get("lastHeard")),
                "snr": subject.get("snr"),
                "hops_away": subject.get("hopsAway"),
                "via_mqtt": subject.get("viaMqtt"),
                "channel": subject.get("channel"),
            }
        metrics = info.get("deviceMetrics") or {}
        return {
            "status": "reachable",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "node_id": node_id,
            "long_name": user.get("longName") or node_id,
            "short_name": user.get("shortName") or "",
            "role": user.get("role"),
            "firmware_version": getattr(metadata, "firmware_version", None),
            "radio": {
                "region": _enum_name(lora, "region"),
                "modem_preset": _enum_name(lora, "modem_preset"),
                "hop_limit": int(lora.hop_limit),
            },
            "network": {
                "udp_broadcast_enabled": bool(int(network.enabled_protocols) & 1),
                "mqtt_enabled": bool(mqtt.enabled),
                "mqtt_root": mqtt.root if mqtt.enabled else None,
            },
            "channels": channels,
            "subject_observation": observation,
            "device_metrics": {
                "channel_utilization": metrics.get("channelUtilization"),
                "air_util_tx": metrics.get("airUtilTx"),
            },
        }
    finally:
        interface.close()


def main() -> int:
    logging.disable(logging.CRITICAL)
    try:
        request = json.loads(sys.stdin.read())
        result = _probe(request)
    except Exception as exc:
        result = {
            "status": "unreachable",
            "error_code": "connection_failed",
            "error": str(exc) or type(exc).__name__,
        }
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
