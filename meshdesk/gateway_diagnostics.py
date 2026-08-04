from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any


def channel_signature(
    nonce: bytes,
    index: int,
    role: int,
    name: str,
    psk: bytes,
) -> str:
    """Create a one-probe channel comparator that is useless after the probe."""
    payload = bytearray()
    payload.extend(int(index).to_bytes(1, "big"))
    payload.extend(int(role).to_bytes(1, "big"))
    encoded_name = name.encode("utf-8")
    payload.extend(len(encoded_name).to_bytes(2, "big"))
    payload.extend(encoded_name)
    payload.extend(len(psk).to_bytes(2, "big"))
    payload.extend(psk)
    return hmac.new(nonce, payload, hashlib.sha256).hexdigest()


ProbeWorker = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class GatewayDiagnostics:
    """Run isolated, bounded, read-only probes for saved TCP gateway profiles."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_workers: int = 4,
        probe_worker: ProbeWorker | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_workers = max_workers
        self._probe_worker = probe_worker or self._subprocess_probe

    def _subprocess_probe(
        self,
        profile: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            **request,
            "host": profile["host"],
            "port": int(profile.get("port") or 4403),
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "meshdesk.gateway_probe_worker"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "error_code": "probe_timeout",
                "error": f"Read-only handshake exceeded {self.timeout_seconds:g} s",
            }
        if completed.returncode != 0:
            return {
                "status": "unreachable",
                "error_code": "probe_failed",
                "error": "The isolated TCP probe did not complete",
            }
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {
                "status": "unreachable",
                "error_code": "invalid_probe_response",
                "error": "The isolated TCP probe returned invalid data",
            }
        return result if isinstance(result, dict) else {
            "status": "unreachable",
            "error_code": "invalid_probe_response",
            "error": "The isolated TCP probe returned invalid data",
        }

    @staticmethod
    def _compatibility(
        active: dict[str, Any],
        observed: dict[str, Any],
    ) -> dict[str, Any]:
        active_radio = active.get("radio") or {}
        gateway_radio = observed.get("radio") or {}
        region_match = (
            active_radio.get("region") == gateway_radio.get("region")
            if active_radio.get("region") and gateway_radio.get("region")
            else None
        )
        preset_match = (
            active_radio.get("modem_preset") == gateway_radio.get("modem_preset")
            if active_radio.get("modem_preset") and gateway_radio.get("modem_preset")
            else None
        )
        active_channels = {
            int(channel["index"]): channel
            for channel in active.get("channels") or []
            if channel.get("enabled")
        }
        shared_channels = []
        for gateway_channel in observed.get("channels") or []:
            if not gateway_channel.get("enabled"):
                continue
            active_channel = active_channels.get(int(gateway_channel["index"]))
            if active_channel is None:
                continue
            signature_match = hmac.compare_digest(
                str(active_channel.get("signature") or ""),
                str(gateway_channel.get("signature") or ""),
            )
            shared_channels.append(
                {
                    "index": int(gateway_channel["index"]),
                    "name": gateway_channel.get("name") or active_channel.get("name") or "",
                    "role": gateway_channel.get("role"),
                    "key_and_name_match": signature_match,
                    "uplink_enabled": bool(gateway_channel.get("uplink_enabled")),
                    "downlink_enabled": bool(gateway_channel.get("downlink_enabled")),
                }
            )
        matching_channels = [
            channel for channel in shared_channels if channel["key_and_name_match"]
        ]
        if region_match is False or preset_match is False:
            verdict = "incompatible"
        elif matching_channels:
            verdict = "compatible"
        elif shared_channels:
            verdict = "channel_mismatch"
        else:
            verdict = "unknown"
        return {
            "verdict": verdict,
            "region_match": region_match,
            "modem_preset_match": preset_match,
            "shared_channels": shared_channels,
            "matching_channel_count": len(matching_channels),
        }

    @staticmethod
    def _public_probe(
        profile: dict[str, Any],
        result: dict[str, Any],
        active: dict[str, Any],
    ) -> dict[str, Any]:
        public = {
            "profile_id": profile["id"],
            "profile_name": profile.get("name") or profile["id"],
            "endpoint": f"{profile.get('host')}:{profile.get('port', 4403)}",
            **result,
        }
        if result.get("status") != "reachable":
            return public
        expected_id = str(profile.get("device_id") or "").lower() or None
        observed_id = str(result.get("node_id") or "").lower() or None
        public["identity"] = {
            "expected_id": expected_id,
            "observed_id": observed_id,
            "match": expected_id == observed_id if expected_id and observed_id else None,
        }
        public["compatibility"] = GatewayDiagnostics._compatibility(active, result)
        for channel in public.get("channels") or []:
            channel.pop("signature", None)
        return public

    def probe(
        self,
        profile_list: list[dict[str, Any]],
        radio: Any,
    ) -> dict[str, Any]:
        nonce = secrets.token_bytes(32)
        active = radio.gateway_diagnostic_context(nonce)
        subject_id = str(active["subject_node_id"]).lower()
        available_tcp_profiles = [
            profile for profile in profile_list if profile.get("transport") == "tcp"
        ]
        tcp_profiles = [
            profile
            for profile in available_tcp_profiles
            if profile.get("diagnostic_observer") is True
        ]
        results_by_id: dict[str, dict[str, Any]] = {}
        eligible = []
        for profile in tcp_profiles:
            profile_device_id = str(profile.get("device_id") or "").lower()
            profile_endpoint = f"{profile.get('host')}:{profile.get('port', 4403)}"
            active_endpoint = (
                active.get("transport") == "tcp"
                and str(active.get("target") or "") == profile_endpoint
            )
            if not profile_device_id:
                results_by_id[profile["id"]] = {
                    "profile_id": profile["id"],
                    "profile_name": profile.get("name") or profile["id"],
                    "endpoint": profile_endpoint,
                    "status": "skipped",
                    "error_code": "unverified_profile",
                    "error": "Connect once to verify this profile identity before probing",
                }
            elif profile_device_id == subject_id or active_endpoint:
                results_by_id[profile["id"]] = {
                    "profile_id": profile["id"],
                    "profile_name": profile.get("name") or profile["id"],
                    "endpoint": profile_endpoint,
                    "status": "skipped",
                    "error_code": "active_device",
                    "error": "This profile is the currently connected radio identity",
                }
            else:
                eligible.append(profile)

        request = {
            "subject_node_id": subject_id,
            "nonce": base64.b64encode(nonce).decode("ascii"),
        }
        if eligible:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(eligible))) as pool:
                futures = {
                    pool.submit(self._probe_worker, profile, request): profile
                    for profile in eligible
                }
                for future in as_completed(futures):
                    profile = futures[future]
                    try:
                        result = future.result()
                    except Exception:
                        result = {
                            "status": "unreachable",
                            "error_code": "probe_failed",
                            "error": "The isolated TCP probe failed",
                        }
                    results_by_id[profile["id"]] = self._public_probe(
                        profile,
                        result,
                        active,
                    )

        results = [results_by_id[profile["id"]] for profile in tcp_profiles]
        return {
            "checked_at": datetime.now(UTC).isoformat(),
            "mode": "on_demand_read_only",
            "subject": {
                "node_id": subject_id,
                "name": active.get("subject_name") or subject_id,
                "transport": active.get("transport"),
            },
            "gateways": results,
            "summary": {
                "available_tcp_profiles": len(available_tcp_profiles),
                "selected_observers": len(tcp_profiles),
                "reachable": sum(item.get("status") == "reachable" for item in results),
                "observed_subject": sum(
                    bool(item.get("subject_observation")) for item in results
                ),
            },
        }
