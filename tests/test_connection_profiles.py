from __future__ import annotations

import json
import stat

import pytest

from meshdesk.connection_profiles import (
    ConnectionIdentityMismatchError,
    ConnectionProfileStore,
)


def test_connection_profile_lifecycle_is_persistent(tmp_path):
    path = tmp_path / "logs" / "connection-profiles.json"
    store = ConnectionProfileStore(path)

    created = store.create(
        {
            "name": "Домашна база",
            "transport": "tcp",
            "host": "172.16.19.176",
            "port": 4403,
        }
    )
    assert store.list()[0]["id"] == created["id"]
    assert store.list()[0]["last_used_at"] is None
    assert store.list()[0]["device_id"] is None

    updated = store.update(
        created["id"],
        {
            "name": "Основна база",
            "transport": "tcp",
            "host": "mesh.local",
            "port": 4403,
        },
    )
    assert updated["name"] == "Основна база"
    assert updated["created_at"] == created["created_at"]

    used = store.mark_used(created["id"])
    assert used["last_used_at"] is not None
    assert ConnectionProfileStore(path).get(created["id"])["host"] == "mesh.local"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    store.delete(created["id"])
    assert store.list() == []


def test_verified_identity_requires_explicit_rebind(tmp_path):
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    profile = store.create(
        {
            "name": "Gateway",
            "transport": "ble",
            "address": "AA:BB:CC:DD:EE:FF",
        }
    )

    verified = store.verify_identity(profile["id"], "!1234ABCD", "Gateway Node")
    assert verified["device_id"] == "!1234abcd"
    assert verified["device_name"] == "Gateway Node"
    assert verified["identity_first_verified_at"]
    first_verified = verified["identity_first_verified_at"]

    verified_again = store.verify_identity(profile["id"], "!1234abcd", "Renamed Gateway")
    assert verified_again["identity_first_verified_at"] == first_verified
    assert verified_again["device_name"] == "Renamed Gateway"

    with pytest.raises(ConnectionIdentityMismatchError) as mismatch:
        store.verify_identity(profile["id"], "!87654321", "Replacement")
    assert mismatch.value.expected_id == "!1234abcd"
    assert mismatch.value.observed_id == "!87654321"

    rebound = store.verify_identity(
        profile["id"],
        "!87654321",
        "Replacement",
        allow_rebind=True,
    )
    assert rebound["device_id"] == "!87654321"
    assert rebound["identity_first_verified_at"] != first_verified


def test_connection_profiles_do_not_accept_incomplete_endpoints(tmp_path):
    store = ConnectionProfileStore(tmp_path / "profiles.json")

    with pytest.raises(ValueError, match="TCP host"):
        store.create({"name": "Broken", "transport": "tcp", "host": ""})
    with pytest.raises(ValueError, match="Bluetooth address"):
        store.create({"name": "Broken", "transport": "ble", "address": ""})


def test_connection_profile_file_is_versioned(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"version": 99, "profiles": []}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Unsupported"):
        ConnectionProfileStore(path).list()
