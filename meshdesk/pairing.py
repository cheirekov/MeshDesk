from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

import pexpect

_ADDRESS = re.compile(r"^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class BluetoothPairer:
    """Drive a BlueZ KeyboardOnly agent while the UI supplies the passkey."""

    def __init__(self, spawn_factory: Callable[..., Any] = pexpect.spawn) -> None:
        self._spawn = spawn_factory
        self._lock = threading.RLock()
        self._generation = 0
        self._state = "idle"
        self._address: str | None = None
        self._error: str | None = None
        self._pin_event = threading.Event()
        self._pin: str | None = None
        self._log: deque[str] = deque(maxlen=20)
        self._child: Any | None = None

    def start(self, address: str, forget_existing: bool = False) -> None:
        address = address.strip().upper()
        if not _ADDRESS.fullmatch(address):
            raise ValueError("Invalid Bluetooth MAC address")
        if shutil.which("bluetoothctl") is None:
            raise RuntimeError("bluetoothctl is not available")

        self.cancel()
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._state = "starting"
            self._address = address
            self._error = None
            self._pin = None
            self._pin_event = threading.Event()
            self._log.clear()
        threading.Thread(
            target=self._worker,
            args=(generation, address, forget_existing),
            name="meshdesk-bluez-pair",
            daemon=True,
        ).start()

    def submit_pin(self, pin: str) -> None:
        pin = pin.strip()
        if not pin.isdigit() or not 1 <= len(pin) <= 16:
            raise ValueError("PIN must contain between 1 and 16 digits")
        with self._lock:
            if self._state not in {"starting", "pairing", "waiting_for_pin", "pin_received"}:
                raise RuntimeError("Bluetooth pairing is not active")
            self._pin = pin
            self._state = "pin_received"
            self._pin_event.set()

    def cancel(self) -> None:
        with self._lock:
            self._generation += 1
            child = self._child
            self._child = None
            self._pin_event.set()
            if self._state not in {"idle", "paired", "error"}:
                self._state = "cancelled"
        if child is not None:
            try:
                child.sendline("quit")
                child.close(force=True)
            except Exception:
                pass

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "address": self._address,
                "error": self._error,
                "log": list(self._log),
            }

    @staticmethod
    def disconnect_device(address: str) -> None:
        """Release a BlueZ connection so the radio resumes BLE advertising."""
        try:
            subprocess.run(
                ["bluetoothctl", "disconnect", address],
                capture_output=True,
                check=False,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def _set(self, generation: int, state: str, error: str | None = None) -> bool:
        with self._lock:
            if generation != self._generation:
                return False
            self._state = state
            self._error = error
            return True

    def _append_log(self, text: str) -> None:
        clean = _ANSI.sub("", text).strip()
        if clean:
            with self._lock:
                self._log.append(clean[-300:])

    def _worker(self, generation: int, address: str, forget_existing: bool) -> None:
        child = None
        try:
            info = subprocess.run(
                ["bluetoothctl", "info", address],
                capture_output=True,
                check=False,
                text=True,
                timeout=8,
            )
            if "Paired: yes" in info.stdout and not forget_existing:
                self.disconnect_device(address)
                self._set(generation, "paired")
                return

            child = self._spawn(
                "bluetoothctl",
                ["--agent", "KeyboardOnly"],
                encoding="utf-8",
                timeout=45,
                env={**os.environ, "TERM": "dumb", "NO_COLOR": "1"},
            )
            child.setecho(False)
            with self._lock:
                if generation != self._generation:
                    child.close(force=True)
                    return
                self._child = child

            child.expect([r"Agent registered", r"\[bluetooth\].*#"], timeout=10)
            if forget_existing:
                child.sendline(f"remove {address}")
                try:
                    child.expect(
                        [r"Device has been removed", r"not available", r"not found"],
                        timeout=8,
                    )
                except pexpect.TIMEOUT:
                    pass

            child.sendline("scan on")
            try:
                if forget_existing:
                    child.expect(re.escape(address), timeout=25)
                else:
                    child.expect([r"Discovery started", re.escape(address)], timeout=12)
            except pexpect.TIMEOUT:
                if forget_existing:
                    raise TimeoutError(
                        "Radio did not reappear after removing the old pairing; "
                        "wake or restart it and try again"
                    ) from None

            if not self._set(generation, "pairing"):
                return
            child.sendline(f"pair {address}")
            self._set(
                generation,
                "pin_received" if self._pin_event.is_set() else "waiting_for_pin",
            )
            pin_sent = False
            while True:
                index = child.expect(
                    [
                        r"(?:Request passkey|Enter passkey[^\r\n]*:|Enter PIN code[^\r\n]*:)",
                        r"Pairing successful",
                        r"AlreadyExists",
                        r"already paired",
                        r"Failed to pair:\s*([^\r\n]+)",
                        r"AuthenticationFailed",
                        pexpect.EOF,
                        pexpect.TIMEOUT,
                    ],
                    timeout=60,
                )
                self._append_log(f"{child.before or ''}{child.after or ''}")
                if index == 0:
                    if pin_sent:
                        continue
                    if not self._set(generation, "waiting_for_pin"):
                        return
                    if not self._pin_event.wait(timeout=120):
                        raise TimeoutError("Timed out waiting for the Bluetooth PIN")
                    with self._lock:
                        if generation != self._generation:
                            return
                        pin = self._pin
                    if not pin:
                        raise RuntimeError("Bluetooth pairing was cancelled")
                    self._set(generation, "pin_received")
                    child.sendline(pin)
                    pin_sent = True
                    continue
                if index in {1, 2, 3}:
                    child.sendline(f"trust {address}")
                    try:
                        child.expect([r"trust succeeded", r"already trusted"], timeout=8)
                    except pexpect.TIMEOUT:
                        pass
                    child.sendline(f"disconnect {address}")
                    try:
                        child.expect(
                            [
                                r"Successful disconnected",
                                r"Connected:\s*no",
                                r"not connected",
                            ],
                            timeout=10,
                        )
                    except pexpect.TIMEOUT:
                        self.disconnect_device(address)
                    self._set(generation, "paired")
                    return
                if index in {4, 5}:
                    detail = child.match.group(1).strip() if index == 4 else "Authentication failed"
                    raise RuntimeError(detail)
                if index == 6:
                    raise RuntimeError("bluetoothctl exited before pairing completed")
                raise TimeoutError(
                    "Bluetooth pairing timed out; wake the radio and ensure it is advertising"
                )
        except Exception as exc:
            self._set(generation, "error", str(exc) or type(exc).__name__)
        finally:
            if child is not None:
                try:
                    child.sendline("scan off")
                    child.sendline("quit")
                    child.close(force=True)
                except Exception:
                    pass
            with self._lock:
                if generation == self._generation:
                    self._child = None
