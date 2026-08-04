from __future__ import annotations

import json
import logging
import sys
import threading
import time
from datetime import UTC, datetime
from typing import Any

from pubsub import pub

from meshdesk.gateway_probe_worker import BoundedTCPInterface


def _emit(record: dict[str, Any], lock: threading.Lock) -> None:
    with lock:
        sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _observe(request: dict[str, Any]) -> None:
    output_lock = threading.Lock()
    expected_id = str(request["expected_node_id"]).lower()
    subject_id = str(request["subject_node_id"]).lower()
    subject_number = int(subject_id.removeprefix("!"), 16)
    interface_holder: dict[str, Any] = {
        "interface": None,
        "armed": False,
        "last_packet": time.monotonic(),
    }

    def on_receive(packet: dict[str, Any], interface: Any) -> None:
        if interface is not interface_holder["interface"] or packet.get("id") is None:
            return
        interface_holder["last_packet"] = time.monotonic()
        if not interface_holder["armed"]:
            return
        packet_from = packet.get("fromId") or packet.get("from")
        if (
            str(packet_from).lower() != subject_id
            and packet_from != subject_number
        ):
            return
        decoded = packet.get("decoded") or {}
        _emit(
            {
                "kind": "packet",
                "seen_at": datetime.now(UTC).isoformat(),
                "packet_id": packet.get("id"),
                "from": packet.get("fromId") or packet.get("from"),
                "to": packet.get("toId") or packet.get("to"),
                "channel": packet.get("channel"),
                "portnum": decoded.get("portnum"),
                "snr": packet.get("rxSnr"),
                "rssi": packet.get("rxRssi"),
                "hop_limit": packet.get("hopLimit"),
                "hop_start": packet.get("hopStart"),
                "relay_node": packet.get("relayNode"),
                "via_mqtt": bool(packet.get("viaMqtt")),
            },
            output_lock,
        )

    pub.subscribe(on_receive, "meshtastic.receive")
    interface = None
    try:
        interface = BoundedTCPInterface(
            hostname=str(request["host"]),
            portNumber=int(request.get("port") or 4403),
            timeout=10,
            connect_timeout=4,
        )
        interface_holder["interface"] = interface
        info = interface.getMyNodeInfo() or {}
        observed_id = str((info.get("user") or {}).get("id") or "").lower()
        if observed_id != expected_id:
            _emit(
                {
                    "kind": "error",
                    "error_code": "identity_mismatch",
                    "error": f"Expected {expected_id}, observed {observed_id or 'unknown'}",
                },
                output_lock,
            )
            return
        _emit({"kind": "syncing", "node_id": observed_id}, output_lock)
        sync_deadline = time.monotonic() + 5
        while (
            time.monotonic() < sync_deadline
            and time.monotonic() - interface_holder["last_packet"] < 0.75
        ):
            time.sleep(0.1)
        interface_holder["armed"] = True
        _emit({"kind": "ready", "node_id": observed_id}, output_lock)
        deadline = time.monotonic() + int(request["duration_seconds"])
        while time.monotonic() < deadline:
            time.sleep(min(0.25, deadline - time.monotonic()))
        _emit({"kind": "complete"}, output_lock)
    finally:
        pub.unsubscribe(on_receive, "meshtastic.receive")
        if interface is not None:
            interface.close()


def main() -> int:
    logging.disable(logging.CRITICAL)
    try:
        request = json.loads(sys.stdin.readline())
        _observe(request)
        return 0
    except Exception as exc:
        lock = threading.Lock()
        _emit(
            {
                "kind": "error",
                "error_code": "connection_failed",
                "error": str(exc) or type(exc).__name__,
            },
            lock,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
