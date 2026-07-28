from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from meshdesk.pairing import BluetoothPairer


def test_existing_bluez_pair_is_detected_without_spawning_agent(monkeypatch):
    monkeypatch.setattr(
        "meshdesk.pairing.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="Paired: yes\n"),
    )

    def unexpected_spawn(*args, **kwargs):
        raise AssertionError("bluetoothctl agent should not be spawned")

    pairer = BluetoothPairer(spawn_factory=unexpected_spawn)
    pairer.start("E0:72:A1:B3:B3:B9")
    for _ in range(50):
        if pairer.status()["state"] != "starting":
            break
        time.sleep(0.01)
    assert pairer.status()["state"] == "paired"


def test_pairing_validates_address_and_pin():
    pairer = BluetoothPairer()
    with pytest.raises(ValueError, match="MAC"):
        pairer.start("not-an-address")
    with pytest.raises(ValueError, match="PIN"):
        pairer.submit_pin("hello")


def test_pin_can_be_submitted_when_bluez_requests_passkey(monkeypatch):
    monkeypatch.setattr(
        "meshdesk.pairing.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="Paired: no\n"),
    )

    class FakeChild:
        def __init__(self):
            self.responses = iter([0, 0, 0, 1, 0, 0])
            self.before = ""
            self.after = "Request passkey"
            self.sent = []

        def setecho(self, value):
            return None

        def sendline(self, value):
            self.sent.append(value)

        def expect(self, patterns, timeout):
            return next(self.responses)

        def close(self, force=False):
            return None

    child = FakeChild()
    pairer = BluetoothPairer(spawn_factory=lambda *args, **kwargs: child)
    pairer.start("E0:72:A1:B3:B3:B9")
    for _ in range(100):
        if pairer.status()["state"] == "waiting_for_pin":
            break
        time.sleep(0.01)
    assert pairer.status()["state"] == "waiting_for_pin"

    pairer.submit_pin("123456")
    for _ in range(100):
        if pairer.status()["state"] == "paired":
            break
        time.sleep(0.01)
    assert pairer.status()["state"] == "paired"
    assert "123456" in child.sent
    assert "disconnect E0:72:A1:B3:B3:B9" in child.sent
