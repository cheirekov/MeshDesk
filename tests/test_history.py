from __future__ import annotations

from meshdesk.history import EncryptedHistory


def test_encrypted_history_round_trip_and_profile_isolation(tmp_path):
    history = EncryptedHistory(tmp_path / "logs", key=b"k" * 32)
    event = {
        "event_id": "event-1",
        "kind": "incoming",
        "text": "secret mesh message",
    }
    history.append("!11111111", event)

    assert history.load("!11111111") == [event]
    assert history.load("!22222222") == []
    ciphertext = (tmp_path / "logs" / "!11111111.events.aes").read_bytes()
    assert b"secret mesh message" not in ciphertext


def test_encrypted_history_generates_private_local_key(tmp_path):
    directory = tmp_path / "logs"
    history = EncryptedHistory(directory)
    history.append("!12345678", {"kind": "outgoing", "text": "hello"})

    key_path = directory / ".history.key"
    assert len(key_path.read_bytes()) == 32
    assert key_path.stat().st_mode & 0o077 == 0


def test_private_records_are_encrypted_and_namespaced(tmp_path):
    history = EncryptedHistory(tmp_path / "logs", key=b"k" * 32)
    backup = {
        "backup_id": "backup-1",
        "channels": [{"protobuf_base64": "very-secret-channel-key"}],
    }

    history.append_private("!11111111", "channel-backups", backup)

    assert history.load_private("!11111111", "channel-backups") == [backup]
    assert history.load_private("!11111111", "other-records") == []
    ciphertext = (
        tmp_path / "logs" / "!11111111.channel-backups.aes"
    ).read_bytes()
    assert b"very-secret-channel-key" not in ciphertext
