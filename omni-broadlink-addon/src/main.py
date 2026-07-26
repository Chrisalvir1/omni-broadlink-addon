import os
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .broadlink_manager import BroadlinkManager

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger("omni.main")

app = FastAPI(title="Omni Broadlink Home Assistant Add-on")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = BroadlinkManager()

class LearnStartRequest(BaseModel):
    ip: str
    mode: str = "ir"

class LearnCancelRequest(BaseModel):
    ip: Optional[str] = None

class SaveRemoteRequest(BaseModel):
    name: str
    ip: str
    type: str = "IR"
    commands: Dict[str, str]
    domain: str = "switch"
    device_type: str = "custom"

class DeleteRemoteRequest(BaseModel):
    name: str

class SendCommandRequest(BaseModel):
    name: str
    command: str

@app.on_event("startup")
async def startup_event():
    _LOGGER.info("Omni Broadlink Add-on backend started.")
    try:
        await manager.scan_devices(force=True)
    except Exception as e:
        _LOGGER.error(f"Error during startup scan: {e}")

@app.get("/api/broadlink/devices")
async def get_broadlink_devices(force: bool = False):
    """Scan and return discovered Broadlink hubs and saved remotes."""
    discovered = await manager.scan_devices(force=force)
    return {
        "discovered": discovered,
        "remotes": manager.remotes
    }

@app.post("/api/broadlink/learn/start")
async def start_learning(req: LearnStartRequest):
    """Start IR or RF learning loop."""
    await manager.start_learning(req.ip, req.mode)
    return {"ok": True, "status": manager.learning_state}

@app.get("/api/broadlink/learn/status")
async def get_learning_status():
    """Poll current learning state."""
    return manager.learning_state

@app.post("/api/broadlink/learn/cancel")
async def cancel_learning(req: LearnCancelRequest):
    """Cancel active learning task."""
    await manager.cancel_learning(req.ip)
    return {"ok": True}

@app.post("/api/broadlink/save")
async def save_remote(req: SaveRemoteRequest):
    """Save a virtual remote control and its commands."""
    if not req.name or not req.ip or not req.commands:
        raise HTTPException(status_code=400, detail="Faltan campos requeridos (name, ip, commands).")
    
    remote = manager.save_remote(
        name=req.name,
        ip=req.ip,
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
