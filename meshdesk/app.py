from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from meshdesk import __version__
from meshdesk.manager import MeshtasticManager

STATIC_DIR = Path(__file__).parent / "static"


class ConnectRequest(BaseModel):
    transport: Literal["tcp", "ble"]
    host: str = "172.16.19.176"
    port: int = Field(default=4403, ge=1, le=65535)
    address: str = ""


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
    ] = "device"
    hop_limit: int | None = Field(default=None, ge=1, le=7)


def create_app(manager: MeshtasticManager | None = None) -> FastAPI:
    radio = manager or MeshtasticManager()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        radio.disconnect()
        if hasattr(radio, "pairer"):
            radio.pairer.cancel()

    api = FastAPI(
        title="MeshDesk",
        version=__version__,
        description="Local Linux Meshtastic UI over native TCP and Bluetooth LE",
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

    @api.post("/api/connect", status_code=202)
    def connect(request: ConnectRequest) -> dict:
        try:
            if request.transport == "tcp":
                radio.connect_tcp(request.host, request.port)
            else:
                radio.connect_ble(request.address)
            return radio.status()
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

    @api.post("/api/node-actions", status_code=202)
    def node_action(request: NodeActionRequest) -> dict:
        try:
            packet = radio.request_node_action(
                request.node_id,
                request.action,
                request.channel,
                request.telemetry_type,
                request.hop_limit,
            )
            return {"packet": packet}
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

    @api.post("/api/messages")
    def send_message(request: MessageRequest) -> dict:
        try:
            packet = radio.send_text(
                request.text,
                request.destination,
                request.channel,
                request.want_ack,
            )
            return {"packet": packet}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc) or type(exc).__name__) from exc

    return api


app = create_app()
