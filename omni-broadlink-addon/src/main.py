import os
import logging
import ipaddress
import json
import re
from ipaddress import IPv4Address
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .broadlink_manager import BroadlinkManager

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger("omni.main")

# The add-on uses host networking for Broadlink UDP discovery. Keep that
# requirement, but only accept UI traffic proxied by HA Ingress and requests
# from the configured Supervisor/add-on network for the compatibility export.
DEFAULT_TRUSTED_PROXY_CIDRS = ("172.30.32.2/32", "127.0.0.1/32", "::1/128")
DEFAULT_TRUSTED_EXPORT_CIDRS = ("172.30.32.0/23", "127.0.0.1/32", "::1/128")


def _trusted_networks(setting: str = "trusted_proxy_cidrs") -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    setting_to_env = {
        "trusted_proxy_cidrs": "BROADLINK_TRUSTED_PROXY_CIDRS",
        "trusted_export_cidrs": "BROADLINK_TRUSTED_EXPORT_CIDRS",
    }
    defaults = {
        "trusted_proxy_cidrs": DEFAULT_TRUSTED_PROXY_CIDRS,
        "trusted_export_cidrs": DEFAULT_TRUSTED_EXPORT_CIDRS,
    }
    raw = os.environ.get(setting_to_env[setting])
    if raw is None:
        try:
            with open("/data/options.json", encoding="utf-8") as options_file:
                raw = json.load(options_file).get(setting)
        except (OSError, ValueError, AttributeError):
            raw = None
    cidrs = [item.strip() for item in (raw or ",".join(defaults[setting])).split(",") if item.strip()]
    try:
        return tuple(ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)
    except ValueError as err:
        raise RuntimeError("BROADLINK_TRUSTED_PROXY_CIDRS contains an invalid CIDR") from err


def _is_trusted_peer(request: Request, *, for_export: bool = False) -> bool:
    peer = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    networks = _trusted_networks("trusted_export_cidrs") if for_export else _trusted_networks()
    return any(address.version == network.version and address in network for network in networks)


async def protect_api(request: Request, call_next):
    is_export = request.url.path == "/api/export/remotes"
    if not _is_trusted_peer(request, for_export=is_export):
        return JSONResponse(status_code=403, content={"detail": "Acceso permitido solo desde Home Assistant."})

    # The export route is intended for local HA add-ons; keep it available to
    # trusted add-on callers while preventing direct LAN access.
    if is_export:
        return await call_next(request)

    ingress_path = request.headers.get("X-Ingress-Path", "")
    ingress_token = ingress_path.removeprefix("/api/hassio_ingress/")
    if (
        request.headers.get("X-Hass-Source") != "core.ingress"
        or not ingress_path.startswith("/api/hassio_ingress/")
        or not ingress_token
        or not re.fullmatch(r"[A-Za-z0-9_-]+", ingress_token)
        or not request.headers.get("X-Remote-User-Id")
    ):
        return JSONResponse(status_code=403, content={"detail": "Sesión autenticada de Home Assistant Ingress requerida."})

    origin = request.headers.get("origin")
    if origin:
        forwarded_host = request.headers.get("x-forwarded-host")
        forwarded_proto = request.headers.get("x-forwarded-proto", "http")
        if not forwarded_host or origin != f"{forwarded_proto}://{forwarded_host}":
            return JSONResponse(status_code=403, content={"detail": "Origen no permitido."})
    return await call_next(request)

manager = BroadlinkManager()


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    _LOGGER.info("Omni Broadlink Add-on backend started.")
    try:
        await manager.scan_devices(force=True)
    except Exception as err:
        _LOGGER.error("Error during startup scan (%s)", err.__class__.__name__)
    yield


app = FastAPI(title="Omni Broadlink Home Assistant Add-on", lifespan=app_lifespan)
app.middleware("http")(protect_api)

class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LearnStartRequest(RequestModel):
    ip: IPv4Address
    mode: str = Field(default="ir", pattern="^(ir|rf)$")

class LearnCancelRequest(RequestModel):
    ip: Optional[IPv4Address] = None

class SaveRemoteRequest(RequestModel):
    name: str = Field(min_length=1, max_length=80)
    ip: IPv4Address
    type: str = Field(default="IR", pattern="^(IR|RF)$")
    commands: Dict[str, str] = Field(min_length=1, max_length=100)
    domain: str = Field(default="switch", pattern="^(switch|light|media_player|climate)$")
    device_type: str = Field(default="custom", min_length=1, max_length=40, pattern="^[a-zA-Z0-9_-]+$")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(not (char.isalnum() or char in " _-") for char in value):
            raise ValueError("El nombre no es válido.")
        return value

    @field_validator("commands")
    @classmethod
    def validate_commands(cls, commands: Dict[str, str]) -> Dict[str, str]:
        if not commands:
            raise ValueError("Debe incluir al menos un comando.")
        for name, code in commands.items():
            if not name.strip() or len(name) > 80 or not re.fullmatch(r"[A-Za-z0-9 _.-]+", name):
                raise ValueError("El nombre de un comando no es válido.")
            if not isinstance(code, str) or len(code) > 65_536:
                raise ValueError("El código del comando es demasiado grande.")
            try:
                import base64
                base64.b64decode(code, validate=True)
            except (ValueError, TypeError):
                raise ValueError("El código debe estar codificado en Base64 válido.") from None
        if sum(map(len, commands.values())) > 1_000_000:
            raise ValueError("El tamaño combinado de los códigos supera el límite permitido.")
        return commands

class DeleteRemoteRequest(RequestModel):
    name: str = Field(min_length=1, max_length=80)

class SendCommandRequest(RequestModel):
    name: str = Field(min_length=1, max_length=80)
    command: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9 _.-]+$")

@app.get("/api/broadlink/devices")
async def get_broadlink_devices(force: bool = False):
    """Scan and return discovered Broadlink hubs and saved remotes."""
    discovered = await manager.scan_devices(force=force)
    return {
        "discovered": discovered,
        # UI needs command names, never the IR/RF payloads themselves.
        "remotes": {
            name: {**remote, "commands": {key: "" for key in remote.get("commands", {})}}
            for name, remote in manager.remotes.items()
        }
    }

@app.post("/api/broadlink/learn/start")
async def start_learning(req: LearnStartRequest):
    """Start IR or RF learning loop."""
    await manager.start_learning(str(req.ip), req.mode)
    return {"ok": True, "status": manager.learning_state}

@app.get("/api/broadlink/learn/status")
async def get_learning_status():
    """Poll current learning state."""
    return manager.learning_state

@app.post("/api/broadlink/learn/cancel")
async def cancel_learning(req: LearnCancelRequest):
    """Cancel active learning task."""
    await manager.cancel_learning(str(req.ip) if req.ip else None)
    return {"ok": True}

@app.post("/api/broadlink/save")
async def save_remote(req: SaveRemoteRequest):
    """Save a virtual remote control and its commands."""
    if not req.name or not req.ip or not req.commands:
        raise HTTPException(status_code=400, detail="Faltan campos requeridos (name, ip, commands).")
    
    remote = manager.save_remote(
        name=req.name,
        ip=str(req.ip),
        remote_type=req.type,
        commands=req.commands,
        domain=req.domain,
        device_type=req.device_type
    )
    return {"ok": True, "remote": remote}

@app.post("/api/broadlink/delete")
async def delete_remote(req: DeleteRemoteRequest):
    """Delete a saved virtual remote control."""
    success = manager.delete_remote(req.name)
    if not success:
        raise HTTPException(status_code=404, detail="Remote no encontrado.")
    return {"ok": True}

@app.post("/api/broadlink/send")
async def send_command(req: SendCommandRequest):
    """Send a specific command signal via Broadlink."""
    remote = manager.remotes.get(req.name)
    if not remote:
        raise HTTPException(status_code=404, detail=f"Control '{req.name}' no encontrado.")
    
    b64_data = remote.get("commands", {}).get(req.command)
    if not b64_data:
        raise HTTPException(status_code=404, detail=f"Comando '{req.command}' no encontrado en el control '{req.name}'.")
    
    success = await manager.send_command(remote["ip"], b64_data)
    if not success:
        raise HTTPException(status_code=500, detail="Error al transmitir señal Broadlink.")
    
    return {"ok": True}

@app.get("/api/export/remotes")
async def export_remotes():
    """Public endpoint to expose learned Broadlink devices to external Add-ons."""
    return {
        "version": "1.0.0",
        "remotes": manager.remotes
    }

# Mount static files for HA Ingress frontend UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
