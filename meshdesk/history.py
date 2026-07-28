from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import re
import secrets
import threading
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

HISTORY_VERSION = 1
DEFAULT_HISTORY_LIMIT = 5000


class EncryptedHistory:
    """Append-only, per-device encrypted event storage."""

    def __init__(
        self,
        directory: Path | str = "logs",
        key: bytes | None = None,
        limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> None:
        self.directory = Path(directory)
        self.limit = limit
        self._lock = threading.Lock()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with contextlib.suppress(PermissionError):
            self.directory.chmod(0o700)
        self._key = key or self._load_or_create_key()
        if len(self._key) != 32:
            raise ValueError("MeshDesk history key must contain exactly 32 bytes")
        self._cipher = AESGCM(self._key)

    def _load_or_create_key(self) -> bytes:
        configured = os.getenv("MESHDESK_HISTORY_KEY", "").strip()
        if configured:
            try:
                if re.fullmatch(r"[0-9a-fA-F]{64}", configured):
                    return bytes.fromhex(configured)
                return base64.urlsafe_b64decode(configured + "=" * (-len(configured) % 4))
            except Exception as exc:
                raise ValueError("MESHDESK_HISTORY_KEY is not valid hex/base64") from exc

        path = self.directory / ".history.key"
        if path.exists():
            return path.read_bytes()
        key = secrets.token_bytes(32)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, key)
        finally:
            os.close(descriptor)
        return key

    @staticmethod
    def _safe_profile(profile_id: str) -> str:
        safe = re.sub(r"[^0-9A-Za-z_.!-]", "_", profile_id)
        if not safe or safe in {".", ".."}:
            raise ValueError("Invalid history profile ID")
        return safe

    def _path(self, profile_id: str) -> Path:
        return self.directory / f"{self._safe_profile(profile_id)}.events.aes"

    @staticmethod
    def _aad(profile_id: str) -> bytes:
        return f"meshdesk-history-v{HISTORY_VERSION}:{profile_id}".encode()

    def append(self, profile_id: str, event: dict[str, Any]) -> None:
        payload = json.dumps(
            {"version": HISTORY_VERSION, "event": event},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        nonce = secrets.token_bytes(12)
        encrypted = nonce + self._cipher.encrypt(nonce, payload, self._aad(profile_id))
        line = base64.urlsafe_b64encode(encrypted) + b"\n"
        path = self._path(profile_id)
        with self._lock:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, line)
            finally:
                os.close(descriptor)

    def load(self, profile_id: str) -> list[dict[str, Any]]:
        path = self._path(profile_id)
        if not path.exists():
            return []
        with self._lock:
            lines = path.read_bytes().splitlines()[-self.limit :]
        events = []
        for line in lines:
            try:
                encrypted = base64.urlsafe_b64decode(line)
                nonce, ciphertext = encrypted[:12], encrypted[12:]
                payload = self._cipher.decrypt(nonce, ciphertext, self._aad(profile_id))
                record = json.loads(payload)
                if record.get("version") == HISTORY_VERSION and isinstance(
                    record.get("event"), dict
                ):
                    events.append(record["event"])
            except Exception:
                logger.warning("Skipping an unreadable MeshDesk history record in %s", path)
        return events
