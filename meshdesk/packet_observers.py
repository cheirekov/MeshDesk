from __future__ import annotations

import copy
import json
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, TextIO


def _now() -> datetime:
    return datetime.now(UTC)


class ObserverProcess(Protocol):
    stdout: TextIO | None

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


ProcessLauncher = Callable[[dict[str, Any], dict[str, Any]], ObserverProcess]


class PacketObserverService:
    """Manage bounded, isolated TCP packet observers without storing payloads."""

    def __init__(
        self,
        *,
        max_observers: int = 4,
        launcher: ProcessLauncher | None = None,
    ) -> None:
        self.max_observers = max_observers
        self._launcher = launcher or self._launch_subprocess
        self._lock = threading.RLock()
        self._session: dict[str, Any] | None = None
        self._processes: dict[str, ObserverProcess] = {}
        self._event_sink: Callable[..., Any] | None = None

    @staticmethod
    def _launch_subprocess(
        profile: dict[str, Any],
        request: dict[str, Any],
    ) -> ObserverProcess:
        return subprocess.Popen(  # noqa: S603 - fixed module, no shell
            [sys.executable, "-m", "meshdesk.packet_observer_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

    @staticmethod
    def _write_request(process: ObserverProcess, request: dict[str, Any]) -> None:
        stdin = getattr(process, "stdin", None)
        if stdin is None:
            return
        stdin.write(json.dumps(request) + "\n")
        stdin.flush()
        stdin.close()

    @staticmethod
    def _eligible_profiles(
        profiles: list[dict[str, Any]],
        status: dict[str, Any],
    ) -> list[dict[str, Any]]:
        subject_id = str(status.get("profile_id") or "").lower()
        active_endpoint = (
            str(status.get("target") or "") if status.get("transport") == "tcp" else None
        )
        eligible = []
        for profile in profiles:
            endpoint = f"{profile.get('host')}:{profile.get('port', 4403)}"
            device_id = str(profile.get("device_id") or "").lower()
            if (
                profile.get("transport") == "tcp"
                and profile.get("diagnostic_observer") is True
                and device_id
                and device_id != subject_id
                and endpoint != active_endpoint
            ):
                eligible.append(profile)
        return eligible

    def start(
        self,
        profiles: list[dict[str, Any]],
        radio: Any,
        duration_seconds: int = 120,
    ) -> dict[str, Any]:
        if not 30 <= duration_seconds <= 300:
            raise ValueError("Observer duration must be between 30 and 300 seconds")
        status = radio.status()
        if status.get("state") != "connected" or not status.get("profile_id"):
            raise RuntimeError("A connected Meshtastic radio is required")
        eligible = self._eligible_profiles(profiles, status)
        if not eligible:
            raise ValueError("No eligible TCP route observers are selected")
        if len(eligible) > self.max_observers:
            raise ValueError(f"At most {self.max_observers} observers can run together")

        self.stop("replaced")
        started = _now()
        session_id = uuid.uuid4().hex
        session = {
            "id": session_id,
            "state": "starting",
            "started_at": started.isoformat(),
            "expires_at": (started + timedelta(seconds=duration_seconds)).isoformat(),
            "ended_at": None,
            "duration_seconds": duration_seconds,
            "subject": {
                "node_id": str(status["profile_id"]).lower(),
                "name": status.get("profile_name") or status["profile_id"],
            },
            "observers": [],
            "sightings": {},
            "stop_reason": None,
        }
        with self._lock:
            self._session = session
            self._processes = {}
            self._event_sink = getattr(radio, "record_observer_sighting", None)

        request = {
            "duration_seconds": duration_seconds,
            "subject_node_id": str(status["profile_id"]).lower(),
        }
        for profile in eligible:
            observer = {
                "profile_id": profile["id"],
                "profile_name": profile.get("name") or profile["id"],
                "endpoint": f"{profile['host']}:{profile.get('port', 4403)}",
                "expected_node_id": str(profile["device_id"]).lower(),
                "observed_node_id": None,
                "status": "starting",
                "error_code": None,
                "error": None,
                "sighting_count": 0,
                "last_seen_at": None,
                "syncing_at": None,
                "ready_at": None,
                "completed_at": None,
            }
            with self._lock:
                session["observers"].append(observer)
            try:
                process = self._launcher(profile, request)
                self._write_request(process, {
                    **request,
                    "host": profile["host"],
                    "port": int(profile.get("port") or 4403),
                    "expected_node_id": profile["device_id"],
                })
            except Exception as exc:
                observer["status"] = "failed"
                observer["error_code"] = "observer_start_failed"
                observer["error"] = str(exc) or type(exc).__name__
                continue
            with self._lock:
                self._processes[profile["id"]] = process
            threading.Thread(
                target=self._read_worker,
                args=(session_id, profile["id"], process),
                name=f"meshdesk-packet-observer-{profile['id'][:8]}",
                daemon=True,
            ).start()
        self._refresh_session_state(session_id)
        return self.status()

    def _observer(self, profile_id: str) -> dict[str, Any] | None:
        if self._session is None:
            return None
        return next(
            (
                observer
                for observer in self._session["observers"]
                if observer["profile_id"] == profile_id
            ),
            None,
        )

    def _read_worker(
        self,
        session_id: str,
        profile_id: str,
        process: ObserverProcess,
    ) -> None:
        stdout = process.stdout
        if stdout is not None:
            for line in stdout:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    self._handle_record(session_id, profile_id, record)
        try:
            return_code = process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            return_code = process.poll()
        with self._lock:
            if self._session is None or self._session["id"] != session_id:
                return
            observer = self._observer(profile_id)
            if observer and observer["status"] in {"starting", "syncing", "ready"}:
                observer["status"] = "completed" if return_code == 0 else "failed"
                observer["completed_at"] = _now().isoformat()
                if observer["status"] == "failed" and not observer["error"]:
                    observer["error_code"] = "observer_process_failed"
                    observer["error"] = "The isolated observer stopped unexpectedly"
            self._processes.pop(profile_id, None)
        self._refresh_session_state(session_id)

    def _handle_record(
        self,
        session_id: str,
        profile_id: str,
        record: dict[str, Any],
    ) -> None:
        evidence_event = None
        with self._lock:
            if self._session is None or self._session["id"] != session_id:
                return
            if self._session["state"] == "stopped":
                return
            observer = self._observer(profile_id)
            if observer is None:
                return
            kind = record.get("kind")
            if kind == "ready":
                observer["status"] = "ready"
                observer["observed_node_id"] = record.get("node_id")
                observer["ready_at"] = _now().isoformat()
            elif kind == "syncing":
                observer["status"] = "syncing"
                observer["observed_node_id"] = record.get("node_id")
                observer["syncing_at"] = _now().isoformat()
            elif kind == "error":
                observer["status"] = "failed"
                observer["error_code"] = record.get("error_code") or "observer_failed"
                observer["error"] = record.get("error") or "Observer failed"
            elif kind == "complete":
                observer["status"] = "completed"
                observer["completed_at"] = _now().isoformat()
            elif kind == "packet":
                evidence_event = self._record_packet(observer, record)
            event_sink = self._event_sink
        if evidence_event is not None and event_sink is not None:
            try:
                event_sink(**evidence_event)
            except Exception:
                pass
        self._refresh_session_state(session_id)

    def _record_packet(
        self,
        observer: dict[str, Any],
        record: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self._session is None or record.get("packet_id") is None:
            return None
        packet_id = str(record["packet_id"])
        seen_at = record.get("seen_at") or _now().isoformat()
        sighting = self._session["sightings"].setdefault(
            packet_id,
            {
                "packet_id": record["packet_id"],
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
                "from": record.get("from"),
                "to": record.get("to"),
                "channel": record.get("channel"),
                "portnum": record.get("portnum"),
                "observers": {},
            },
        )
        sighting["last_seen_at"] = seen_at
        first_observation = observer["profile_id"] not in sighting["observers"]
        evidence = sighting["observers"].setdefault(
            observer["profile_id"],
            {
                "profile_id": observer["profile_id"],
                "profile_name": observer["profile_name"],
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
                "count": 0,
                "via_mqtt": False,
            },
        )
        evidence.update(
            {
                "last_seen_at": seen_at,
                "count": evidence["count"] + 1,
                "via_mqtt": evidence["via_mqtt"] or bool(record.get("via_mqtt")),
                "snr": record.get("snr"),
                "rssi": record.get("rssi"),
                "hop_limit": record.get("hop_limit"),
                "hop_start": record.get("hop_start"),
                "relay_node": record.get("relay_node"),
            }
        )
        observer["sighting_count"] += 1
        observer["last_seen_at"] = seen_at
        while len(self._session["sightings"]) > 1000:
            oldest = next(iter(self._session["sightings"]))
            del self._session["sightings"][oldest]
        if not first_observation:
            return None
        return {
            "session_id": self._session["id"],
            "subject_node_id": self._session["subject"]["node_id"],
            "observer_profile_id": observer["profile_id"],
            "observer_profile_name": observer["profile_name"],
            "packet_id": record["packet_id"],
            "seen_at": seen_at,
            "packet_from": record.get("from"),
            "packet_to": record.get("to"),
            "channel": record.get("channel"),
            "portnum": record.get("portnum"),
            "via_mqtt": bool(record.get("via_mqtt")),
            "snr": record.get("snr"),
            "rssi": record.get("rssi"),
            "hop_limit": record.get("hop_limit"),
            "hop_start": record.get("hop_start"),
            "relay_node": record.get("relay_node"),
        }

    def _refresh_session_state(self, session_id: str) -> None:
        with self._lock:
            if self._session is None or self._session["id"] != session_id:
                return
            statuses = {observer["status"] for observer in self._session["observers"]}
            if "ready" in statuses:
                self._session["state"] = "active"
            elif statuses and statuses <= {"completed", "failed", "stopped"}:
                self._session["state"] = "completed"
                self._session["ended_at"] = (
                    self._session.get("ended_at") or _now().isoformat()
                )
            else:
                self._session["state"] = "starting"

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._session is None:
                return {"state": "idle", "observers": [], "sightings": []}
            result = copy.deepcopy(self._session)
        result["sightings"] = [
            {
                **sighting,
                "observers": list(sighting["observers"].values()),
            }
            for sighting in result["sightings"].values()
        ]
        result["sightings"].sort(key=lambda item: item["last_seen_at"], reverse=True)
        return result

    def stop(self, reason: str = "operator") -> dict[str, Any]:
        with self._lock:
            session = self._session
            processes = list(self._processes.items())
            self._processes = {}
            if session is None:
                return {"state": "idle", "observers": [], "sightings": []}
            session["state"] = "stopped"
            session["stop_reason"] = reason
            session["ended_at"] = _now().isoformat()
            for observer in session["observers"]:
                if observer["status"] in {"starting", "syncing", "ready"}:
                    observer["status"] = "stopped"
                    observer["completed_at"] = session["ended_at"]
        for _, process in processes:
            if process.poll() is not None:
                continue
            process.terminate()
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.kill()
        return self.status()
