from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from meshdesk import __version__
from meshdesk.connection_profiles import (
    ConnectionIdentityMismatchError,
    ConnectionProfileStore,
)
from meshdesk.discovery import SerialDiscovery, TcpDiscovery
from meshdesk.manager import MeshtasticManager, RequestCooldownError

STATIC_DIR = Path(__file__).parent / "static"


class ConnectRequest(BaseModel):
    transport: Literal["tcp", "ble", "serial"]
    host: str = "172.16.19.176"
    port: int = Field(default=4403, ge=1, le=65535)
    address: str = ""
    device: str = ""
    connection_profile_id: str | None = None


class ConnectionProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    transport: Literal["tcp", "ble", "serial"]
    host: str = ""
    port: int = Field(default=4403, ge=1, le=65535)
    address: str = ""
    device: str = ""
    auto_reconnect: bool = False


class ConnectionIdentityRequest(BaseModel):
    allow_rebind: bool = False


class MessageRequest(BaseModel):
    text: str
    destination: str = "^all"
    channel: int = Field(default=0, ge=0, le=7)
    want_ack: bool = True


class PairRequest(BaseModel):
    address: str
    forget_existing: bool = False


class PinRequest(BaseModel):
    pin: str


class ConfigRequest(BaseModel):
    section: str
    values: dict[str, Any]
    node_id: str | None = None


class ConfigImportRequest(BaseModel):
    document: dict[str, Any]
    node_id: str | None = None


class RemoteConfigRequest(BaseModel):
    node_id: str
    section: str


class NodeActionRequest(BaseModel):
    node_id: str
    action: Literal[
        "traceroute",
        "telemetry",
        "position",
        "user_info",
        "neighbor_info",
        "favorite",
        "unfavorite",
        "ignore",
        "unignore",
    ]
    channel: int = Field(default=0, ge=0, le=7)
    telemetry_type: Literal[
        "device",
        "environment",
        "air_quality",
        "power",
        "local_stats",
        "host",
        "pax",
    ] = "device"
    hop_limit: int | None = Field(default=None, ge=1, le=7)
    managed_node_id: str | None = None


class AdminActionRequest(BaseModel):
    action: Literal[
        "reboot",
        "shutdown",
        "reset_nodedb",
        "factory_reset_config",
        "factory_reset_device",
    ]
    node_id: str | None = None
    preserve_node_preferences: bool = False


class HistoryReplayRequest(BaseModel):
    window_minutes: int | None = Field(default=None, ge=1, le=43200)
    max_messages: int | None = Field(default=None, ge=1, le=500)


class ChannelUpdateRequest(BaseModel):
    role: Literal["PRIMARY", "SECONDARY", "DISABLED"]
    name: str = Field(default="", max_length=10)
    psk_mode: Literal["unchanged", "random", "default", "none", "custom"] = (
        "unchanged"
    )
    psk: str = Field(default="", max_length=128)
    uplink_enabled: bool = False
    downlink_enabled: bool = False
    position_precision: int = Field(default=0, ge=0, le=32)


def create_app(
    manager: MeshtasticManager | None = None,
    connection_profiles: ConnectionProfileStore | None = None,
    tcp_discovery: TcpDiscovery | None = None,
    serial_discovery: SerialDiscovery | None = None,
) -> FastAPI:
    radio = manager or MeshtasticManager()
    profiles = connection_profiles or ConnectionProfileStore()
    discovery = tcp_discovery or TcpDiscovery()
    usb_discovery = serial_discovery or SerialDiscovery()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        radio.disconnect()
        if hasattr(radio, "pairer"):
            radio.pairer.cancel()

    api = FastAPI(
        title="MeshDesk",
        version=__version__,
        description="Local Linux Meshtastic UI over TCP, Bluetooth LE and USB Serial",
        lifespan=lifespan,
    )
    api.state.radio = radio

    @api.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "index.html",
            headers={"Cache-Control": "no-store"},
        )

    @api.get("/app.js", include_in_schema=False)
    def javascript() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "app.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @api.get("/style.css", include_in_schema=False)
    def stylesheet() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "style.css",
            media_type="text/css",
            headers={"Cache-Control": "no-store"},
        )

    @api.get("/api/status")
    def status() -> dict:
        return radio.status()

    @api.get("/api/connection-profiles")
    def list_connection_profiles() -> dict:
        try:
            return {"profiles": profiles.list()}
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @api.get("/api/discovery/tcp")
    def discover_tcp(timeout: float = Query(default=3.0, ge=0.5, le=10)) -> dict:
        try:
            return {"devices": discovery.discover(timeout)}
        except (OSError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"mDNS discovery is unavailable: {exc}",
            ) from exc

    @api.get("/api/discovery/serial")
    def discover_serial() -> dict:
        try:
            return {"devices": usb_discovery.discover()}
        except (OSError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"USB Serial discovery is unavailable: {exc}",
            ) from exc

    @api.post("/api/connection-profiles", status_code=201)
    def create_connection_profile(request: ConnectionProfileRequest) -> dict:
        try:
            return {"profile": profiles.create(request.model_dump())}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.put("/api/connection-profiles/{profile_id}")
    def update_connection_profile(
        profile_id: str,
        request: ConnectionProfileRequest,
    ) -> dict:
        try:
            return {"profile": profiles.update(profile_id, request.model_dump())}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Connection profile not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.delete("/api/connection-profiles/{profile_id}", status_code=204)
    def delete_connection_profile(profile_id: str) -> None:
        try:
            profiles.delete(profile_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Connection profile not found") from exc

    @api.post("/api/connection-profiles/{profile_id}/verify")
    def verify_connection_profile(
        profile_id: str,
        request: ConnectionIdentityRequest,
    ) -> dict:
        try:
            profile = profiles.get(profile_id)
            current = radio.status()
            if current.get("state") != "connected" or not current.get("profile_id"):
                raise HTTPException(
                    status_code=409,
                    detail="A connected Meshtastic radio is required for identity verification",
                )
            expected_target = (
                f"{profile['host']}:{profile['port']}"
                if profile["transport"] == "tcp"
                else profile["address"]
                if profile["transport"] == "ble"
                else profile["device"]
            )
            actual_target = str(current.get("target") or "")
            target_matches = (
                current.get("transport") == profile["transport"]
                and (
                    actual_target.casefold() == expected_target.casefold()
                    if profile["transport"] == "ble"
                    else actual_target == expected_target
                )
            )
            if not target_matches:
                raise HTTPException(
                    status_code=409,
                    detail="The connected endpoint does not match this profile",
                )
            verified = profiles.verify_identity(
                profile_id,
                str(current["profile_id"]),
                current.get("profile_name"),
                allow_rebind=request.allow_rebind,
            )
            return {"profile": verified}
        except ConnectionIdentityMismatchError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "identity_mismatch",
                    "message": str(exc),
                    "expected_id": exc.expected_id,
                    "expected_name": exc.expected_name,
                    "observed_id": exc.observed_id,
                    "observed_name": exc.observed_name,
                },
            ) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Connection profile not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/api/connect", status_code=202)
    def connect(request: ConnectRequest) -> dict:
        try:
            profile = None
            if request.connection_profile_id:
                profile = profiles.get(request.connection_profile_id)
                endpoint_matches = (
                    profile["transport"] == request.transport
                    and (
                        (
                            request.transport == "tcp"
                            and profile["host"] == request.host.strip()
                            and profile["port"] == request.port
                        )
                        or (
                            request.transport == "ble"
                            and profile["address"] == request.address.strip()
                        )
                        or (
                            request.transport == "serial"
                            and profile["device"] == request.device.strip()
                        )
                    )
                )
                if not endpoint_matches:
                    raise HTTPException(
                        status_code=409,
                        detail="Connection fields differ from the saved profile",
                    )
            if request.transport == "tcp":
                radio.connect_tcp(
                    request.host,
                    request.port,
                    auto_reconnect=bool(profile and profile.get("auto_reconnect")),
                    expected_device_id=profile.get("device_id") if profile else None,
                )
            elif request.transport == "ble":
                radio.connect_ble(
                    request.address,
                    auto_reconnect=bool(profile and profile.get("auto_reconnect")),
                    expected_device_id=profile.get("device_id") if profile else None,
                )
            else:
                radio.connect_serial(
                    request.device,
                    auto_reconnect=bool(profile and profile.get("auto_reconnect")),
                    expected_device_id=profile.get("device_id") if profile else None,
                )
            if request.connection_profile_id:
                profiles.mark_used(request.connection_profile_id)
            return radio.status()
        except HTTPException:
            raise
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Connection profile not found") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/api/disconnect")
    def disconnect() -> dict:
        radio.disconnect()
        return radio.status()

    @api.get("/api/ble/scan")
    def scan_ble() -> dict:
        try:
            return {"devices": radio.scan_ble()}
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc) or type(exc).__name__) from exc

    @api.get("/api/nodes")
    def nodes() -> dict:
        return {"nodes": radio.nodes()}

    @api.get("/api/channels")
    def channels() -> dict:
        return {"channels": radio.channels()}

    @api.get("/api/channel-slots")
    def channel_slots() -> dict:
        return {"channels": radio.channel_slots()}

    @api.get("/api/channel-slots/{index}/psk", include_in_schema=False)
    def channel_psk(index: int) -> JSONResponse:
        try:
            return JSONResponse(
                radio.channel_psk(index),
                headers={
                    "Cache-Control": "no-store, max-age=0",
                    "Pragma": "no-cache",
                },
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=str(exc) or type(exc).__name__,
            ) from exc

    @api.put("/api/channel-slots/{index}")
    def update_channel(index: int, request: ChannelUpdateRequest) -> dict:
        try:
            return {
                "channels": radio.update_channel(
                    index,
                    request.role,
                    request.name,
                    request.psk_mode,
                    request.psk,
                    request.uplink_enabled,
                    request.downlink_enabled,
                    request.position_precision,
                )
            }
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=str(exc) or type(exc).__name__,
            ) from exc

    @api.post("/api/node-actions", status_code=202)
    def node_action(request: NodeActionRequest) -> dict:
        try:
            packet = radio.request_node_action(
                request.node_id,
                request.action,
                request.channel,
                request.telemetry_type,
                request.hop_limit,
                request.managed_node_id,
            )
            return {"packet": packet}
        except RequestCooldownError as exc:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "request_cooldown",
                    "action": exc.action,
                    "scope": exc.scope,
                    "remaining_seconds": round(exc.remaining_seconds, 1),
                    "message": str(exc),
                },
                headers={"Retry-After": str(max(1, int(exc.remaining_seconds + 0.999)))},
            ) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc) or type(exc).__name__) from exc

    @api.post("/api/ble/pair", status_code=202)
    def start_pairing(request: PairRequest) -> dict:
        try:
            radio.pairer.start(request.address, request.forget_existing)
            return radio.pairer.status()
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.get("/api/ble/pair")
    def pairing_status() -> dict:
        return radio.pairer.status()

    @api.post("/api/ble/pair/pin")
    def pairing_pin(request: PinRequest) -> dict:
        try:
            radio.pairer.submit_pin(request.pin)
            return radio.pairer.status()
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.delete("/api/ble/pair")
    def cancel_pairing() -> dict:
        radio.pairer.cancel()
        return radio.pairer.status()

    @api.get("/api/config")
    def get_config(node_id: str | None = None) -> dict:
        try:
            return radio.config(node_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc) or type(exc).__name__) from exc

    @api.put("/api/config")
    def update_config(request: ConfigRequest) -> dict:
        try:
            radio.update_config(request.section, request.values, request.node_id)
            return radio.config(request.node_id)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc) or type(exc).__name__) from exc

    @api.post("/api/remote-admin/config", status_code=202)
    def request_remote_config(request: RemoteConfigRequest) -> dict:
        try:
            radio.request_remote_config(request.node_id, request.section)
            return {"accepted": True}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc) or type(exc).__name__) from exc

    @api.get("/api/config/export")
    def export_config(node_id: str | None = None) -> dict:
        try:
            return radio.export_config(node_id)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/api/config/import")
    def import_config(request: ConfigImportRequest) -> dict:
        try:
            return radio.import_config(request.document, request.node_id)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc) or type(exc).__name__) from exc

    @api.get("/api/events")
    def events(after: int = Query(default=0, ge=0)) -> dict:
        return {"events": radio.events(after)}

    @api.get("/api/history")
    def history() -> dict:
        return {"events": radio.history()}

    @api.post("/api/history/replay", status_code=202)
    def replay_history(request: HistoryReplayRequest) -> dict:
        try:
            packet = radio.request_history_replay(
                request.window_minutes,
                request.max_messages,
            )
            return {"accepted": True, "packet": packet}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc) or type(exc).__name__) from exc

    @api.post("/api/administration", status_code=202)
    def administration(request: AdminActionRequest) -> dict:
        try:
            radio.request_admin_action(
                request.action,
                request.node_id,
                request.preserve_node_preferences,
            )
            return {"accepted": True}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc) or type(exc).__name__) from exc

    @api.post("/api/messages")
    def send_message(request: MessageRequest) -> dict:
        try:
            sender = getattr(radio, "queue_text", radio.send_text)
            result = sender(
                request.text,
                request.destination,
                request.channel,
                request.want_ack,
            )
            return result if "client_id" in result else {"packet": result}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc) or type(exc).__name__) from exc

    return api


app = create_app()
