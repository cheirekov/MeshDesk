from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ConnectionIdentityMismatchError(ValueError):
    def __init__(
        self,
        expected_id: str,
        observed_id: str,
        expected_name: str | None,
        observed_name: str | None,
    ) -> None:
        super().__init__(
            f"Profile expects {expected_name or expected_id}, "
            f"but the connected radio is {observed_name or observed_id}"
        )
        self.expected_id = expected_id
        self.observed_id = observed_id
        self.expected_name = expected_name
        self.observed_name = observed_name


class ConnectionProfileStore:
    """Persist non-secret connection endpoints as a small versioned JSON document."""

    VERSION = 1

    def __init__(self, path: Path | str = "logs/connection-profiles.json") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    @staticmethod
    def _normalized(values: dict[str, Any]) -> dict[str, Any]:
        name = str(values.get("name") or "").strip()
        transport = str(values.get("transport") or "").strip().lower()
        host = str(values.get("host") or "").strip()
        address = str(values.get("address") or "").strip()
        try:
            port = int(values.get("port", 4403))
        except (TypeError, ValueError) as exc:
            raise ValueError("Port must be a number") from exc

        if not name:
            raise ValueError("Profile name is required")
        if len(name) > 80:
            raise ValueError("Profile name must be at most 80 characters")
        if transport not in {"tcp", "ble"}:
            raise ValueError("Transport must be tcp or ble")
        if not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        if transport == "tcp" and not host:
            raise ValueError("TCP host is required")
        if transport == "ble" and not address:
            raise ValueError("Bluetooth address is required")

        return {
            "name": name,
            "transport": transport,
            "host": host if transport == "tcp" else "",
            "port": port if transport == "tcp" else 4403,
            "address": address if transport == "ble" else "",
        }

    def _load_unlocked(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Connection profile file cannot be read: {exc}") from exc
        if not isinstance(document, dict) or document.get("version") != self.VERSION:
            raise RuntimeError("Unsupported connection profile file format")
        profiles = document.get("profiles")
        if not isinstance(profiles, list):
            raise RuntimeError("Connection profile file has no valid profiles list")
        result = {}
        for profile in profiles:
            if isinstance(profile, dict) and isinstance(profile.get("id"), str):
                result[profile["id"]] = profile
        return result

    def _write_unlocked(self, profiles: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "version": self.VERSION,
            "profiles": list(profiles.values()),
        }
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            profiles = list(self._load_unlocked().values())
        return sorted(
            profiles,
            key=lambda profile: (
                profile.get("last_used_at") or "",
                profile.get("updated_at") or "",
            ),
            reverse=True,
        )

    def get(self, profile_id: str) -> dict[str, Any]:
        with self._lock:
            profile = self._load_unlocked().get(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        return dict(profile)

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalized(values)
        timestamp = _now()
        profile = {
            "id": uuid.uuid4().hex,
            **normalized,
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_used_at": None,
            "device_id": None,
            "device_name": None,
            "identity_first_verified_at": None,
            "identity_last_verified_at": None,
        }
        with self._lock:
            profiles = self._load_unlocked()
            profiles[profile["id"]] = profile
            self._write_unlocked(profiles)
        return dict(profile)

    def update(self, profile_id: str, values: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalized(values)
        with self._lock:
            profiles = self._load_unlocked()
            current = profiles.get(profile_id)
            if current is None:
                raise KeyError(profile_id)
            profile = {
                **current,
                **normalized,
                "id": profile_id,
                "updated_at": _now(),
            }
            profiles[profile_id] = profile
            self._write_unlocked(profiles)
        return dict(profile)

    def delete(self, profile_id: str) -> None:
        with self._lock:
            profiles = self._load_unlocked()
            if profile_id not in profiles:
                raise KeyError(profile_id)
            del profiles[profile_id]
            self._write_unlocked(profiles)

    def mark_used(self, profile_id: str) -> dict[str, Any]:
        with self._lock:
            profiles = self._load_unlocked()
            profile = profiles.get(profile_id)
            if profile is None:
                raise KeyError(profile_id)
            profile = {
                **profile,
                "last_used_at": _now(),
            }
            profiles[profile_id] = profile
            self._write_unlocked(profiles)
        return dict(profile)

    def verify_identity(
        self,
        profile_id: str,
        device_id: str,
        device_name: str | None,
        *,
        allow_rebind: bool = False,
    ) -> dict[str, Any]:
        device_id = device_id.strip().lower()
        device_name = (device_name or "").strip() or None
        if not re.fullmatch(r"![0-9a-f]{8}", device_id):
            raise ValueError("Connected radio did not provide a valid Meshtastic node ID")

        with self._lock:
            profiles = self._load_unlocked()
            current = profiles.get(profile_id)
            if current is None:
                raise KeyError(profile_id)
            expected_id = (current.get("device_id") or "").lower() or None
            if expected_id and expected_id != device_id and not allow_rebind:
                raise ConnectionIdentityMismatchError(
                    expected_id,
                    device_id,
                    current.get("device_name"),
                    device_name,
                )

            timestamp = _now()
            first_verified = current.get("identity_first_verified_at")
            if not expected_id or expected_id != device_id:
                first_verified = timestamp
            profile = {
                **current,
                "device_id": device_id,
                "device_name": device_name or current.get("device_name") or device_id,
                "identity_first_verified_at": first_verified,
                "identity_last_verified_at": timestamp,
            }
            profiles[profile_id] = profile
            self._write_unlocked(profiles)
        return dict(profile)
