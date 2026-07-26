import logging
import asyncio
import base64
import time
import json
import os
import requests
import broadlink
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_LOGGER = logging.getLogger("omni.broadlink")

STORAGE_PATH = "/data/broadlink_remotes.json"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
HA_API_URL = "http://supervisor/core/api"

class BroadlinkManager:
    def __init__(self, storage_path: str = STORAGE_PATH):
        self.storage_path = storage_path
        self.discovered_devices: Dict[str, Any] = {}
        self._operation_lock = asyncio.Lock()
        self._learning_task: Optional[asyncio.Task] = None
        self._last_scan_at = 0.0
        self._scan_ttl = 30.0
        self.learning_state = {
            "status": "idle",
            "captured_data": None,
            "error_msg": None,
            "mode": None,
            "phase": None,
            "attempts": 0,
            "last_error": None,
            "frequency": None
        }
        self.remotes: Dict[str, Any] = self._load_remotes()
        # Register entities in HA at startup
        self.sync_all_ha_entities()

    def _load_remotes(self) -> Dict[str, Any]:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                _LOGGER.error(f"Error loading remotes from {self.storage_path}: {e}")
        return {}

    def _save_remotes(self):
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.remotes, f, indent=2, ensure_ascii=False)
            _LOGGER.info(f"Saved {len(self.remotes)} remotes to {self.storage_path}")
        except Exception as e:
            _LOGGER.error(f"Error saving remotes to {self.storage_path}: {e}")

    def sync_all_ha_entities(self):
        """Sync all saved remotes as entities in Home Assistant via REST API."""
        if not SUPERVISOR_TOKEN:
            _LOGGER.info("SUPERVISOR_TOKEN not present. Skipping direct Home Assistant API sync.")
            return
        
        headers = {
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json"
        }

        for name, remote in self.remotes.items():
            slug = name.lower().replace(" ", "_").replace("-", "_")
            domain = remote.get("domain", "switch")
            commands = remote.get("commands", {})

            # 1. Main Device Entity State
            main_entity_id = f"{domain}.omni_broadlink_{slug}"
            state_data = {
                "state": "off",
                "attributes": {
                    "friendly_name": f"Omni Broadlink {name}",
                    "ip": remote.get("ip"),
                    "type": remote.get("type"),
                    "device_type": remote.get("device_type"),
                    "commands_count": len(commands),
                    "icon": "mdi:remote"
                }
            }
            try:
                requests.post(f"{HA_API_URL}/states/{main_entity_id}", headers=headers, json=state_data, timeout=3)
            except Exception as e:
                _LOGGER.debug(f"Failed to post state for {main_entity_id}: {e}")

            # 2. Individual Button Entities in HA
            for btn_key in commands.keys():
                btn_entity_id = f"button.omni_broadlink_{slug}_{btn_key}"
                btn_state_data = {
                    "state": "off",
                    "attributes": {
                        "friendly_name": f"{name} - {btn_key.replace('_', ' ').title()}",
                        "remote_name": name,
                        "button_key": btn_key,
                        "ip": remote.get("ip"),
                        "icon": "mdi:remote-desktop"
                    }
                }
                try:
                    requests.post(f"{HA_API_URL}/states/{btn_entity_id}", headers=headers, json=btn_state_data, timeout=3)
                except Exception as e:
                    _LOGGER.debug(f"Failed to post button entity {btn_entity_id}: {e}")

    def _set_learning_state(self, status: str, **extra):
        self.learning_state = {
            "status": status,
            "captured_data": extra.pop("captured_data", None),
            "error_msg": extra.pop("error_msg", None),
            "mode": extra.pop("mode", self.learning_state.get("mode")),
            "phase": extra.pop("phase", self.learning_state.get("phase")),
            "attempts": extra.pop("attempts", self.learning_state.get("attempts", 0)),
            "last_error": extra.pop("last_error", self.learning_state.get("last_error")),
            "frequency": extra.pop("frequency", self.learning_state.get("frequency")),
            **extra
        }

    async def scan_devices(self, force: bool = False) -> Dict[str, Any]:
        if self.learning_state.get("status") in {"active_learning", "active_learning_rf_packet"}:
            return self.discovered_devices

        now = time.monotonic()
        if not force and self.discovered_devices and now - self._last_scan_at < self._scan_ttl:
            return self.discovered_devices

        try:
            async with self._operation_lock:
                if self.learning_state.get("status") in {"active_learning", "active_learning_rf_packet"}:
                    return self.discovered_devices
                now = time.monotonic()
                if not force and self.discovered_devices and now - self._last_scan_at < self._scan_ttl:
                    return self.discovered_devices

                _LOGGER.info("Scanning for Broadlink devices on local LAN...")
                devices = await asyncio.to_thread(broadlink.discover, timeout=3)
                self.discovered_devices.clear()
                for dev in devices:
                    try:
                        await asyncio.to_thread(dev.auth)
                        mac_str = "".join(f"{b:02x}" for b in dev.mac)
                        self.discovered_devices[dev.host[0]] = {
                            "ip": dev.host[0],
                            "port": dev.host[1],
                            "mac": mac_str,
                            "name": getattr(dev, "name", None) or "Broadlink Device",
                            "model": getattr(dev, "model", None) or "Generic Broadlink",
                            "type": getattr(dev, "type", 0)
                        }
                    except Exception as e:
                        _LOGGER.error(f"Failed to authenticate Broadlink device at {dev.host[0]}: {e}")
                self._last_scan_at = time.monotonic()

            _LOGGER.info(f"Broadlink scan complete. Found {len(self.discovered_devices)} device(s).")
            return self.discovered_devices
        except Exception as e:
            _LOGGER.error(f"Error during Broadlink discovery: {e}")
            return {}

    async def start_learning(self, ip: str, mode: str = "ir"):
        if self._learning_task and not self._learning_task.done():
            self._learning_task.cancel()

        mode = (mode or "ir").lower()
        self._set_learning_state(
            "active_learning",
            mode=mode,
            phase="starting",
            attempts=0,
            last_error=None,
            frequency=None
        )
        self._learning_task = asyncio.create_task(self._learning_loop(ip, mode))

    async def cancel_learning(self, ip: Optional[str] = None):
        if self._learning_task and not self._learning_task.done():
            self._learning_task.cancel()
        await self._cancel_device_learning(ip)
        self._set_learning_state("idle", mode=None, phase=None, attempts=0, last_error=None, frequency=None)

    async def _cancel_device_learning(self, ip: Optional[str] = None):
        try:
            devices = await asyncio.to_thread(broadlink.discover, timeout=2)
            for dev in devices:
                if ip and dev.host[0] != ip:
                    continue
                await asyncio.to_thread(dev.auth)
                if hasattr(dev, "cancel_sweep_frequency"):
                    await asyncio.to_thread(dev.cancel_sweep_frequency)
        except Exception as e:
            _LOGGER.info(f"Broadlink learning cancel ignored: {e}")

    async def _learning_loop(self, ip: str, mode: str):
        try:
            async with self._operation_lock:
                await self._learning_loop_locked(ip, mode)
        except asyncio.CancelledError:
            self._set_learning_state("idle", phase=None, error_msg=None)
        except Exception as e:
            _LOGGER.error(f"Error in Broadlink learning loop: {e}")
            self._set_learning_state("error", error_msg=str(e), last_error=str(e))

    async def _learning_loop_locked(self, ip: str, mode: str):
        try:
            devices = await asyncio.to_thread(broadlink.discover, timeout=2)
            dev = None
            for d in devices:
                if d.host[0] == ip:
                    dev = d
                    break

            if not dev:
                self._set_learning_state("error", error_msg=f"Dispositivo con IP {ip} no encontrado en la red.")
                return

            await asyncio.to_thread(dev.auth)

            if mode == "ir":
                _LOGGER.info(f"Iniciando aprendizaje IR en {ip}")
                await asyncio.to_thread(dev.enter_learning)
                self._set_learning_state("active_learning", mode="ir", phase="ir_waiting", attempts=0, last_error=None)

                for attempt in range(90):
                    await asyncio.sleep(0.5)
                    try:
                        data = await asyncio.to_thread(dev.check_data)
                        if data:
                            b64_data = base64.b64encode(data).decode('utf-8')
                            self._set_learning_state(
                                "captured",
                                mode="ir",
                                phase="captured",
                                captured_data=b64_data,
                                error_msg=None,
                                attempts=attempt + 1,
                                last_error=None
                            )
                            _LOGGER.info(f"Código IR capturado exitosamente ({len(data)} bytes).")
                            return
                    except Exception as e:
                        err = str(e) or e.__class__.__name__
                        self._set_learning_state(
                            "active_learning",
                            mode="ir",
                            phase="ir_waiting",
                            attempts=attempt + 1,
                            last_error=err
                        )

                self._set_learning_state("error", mode="ir", phase="timeout", error_msg="Tiempo de espera agotado: No se recibió señal IR en 45 segundos.")
                await self._cancel_device_learning(ip)

            elif mode == "rf":
                _LOGGER.info(f"Iniciando barrido de frecuencia RF en {ip}")
                await asyncio.to_thread(dev.sweep_frequency)
                self._set_learning_state("active_learning", mode="rf", phase="rf_sweep", attempts=0, last_error=None)

                frequency_found = False
                frequency = None
                for attempt in range(60):
                    await asyncio.sleep(0.5)
                    try:
                        found, frequency = await asyncio.to_thread(dev.check_frequency)
                        if found:
                            if frequency and frequency > 0.0:
                                frequency_found = True
                                self._set_learning_state(
                                    "active_learning",
                                    mode="rf",
                                    phase="rf_frequency_found",
                                    attempts=attempt + 1,
                                    frequency=frequency,
                                    last_error=None
                                )
                                break
                            else:
                                self._set_learning_state(
                                    "error",
                                    mode="rf",
                                    phase="rf_sweep_failed",
                                    error_msg="No se pudo detectar la frecuencia RF. Mantenga presionado el botón del control."
                                )
                                await self._cancel_device_learning(ip)
                                return
                        self._set_learning_state("active_learning", mode="rf", phase="rf_sweep", attempts=attempt + 1, frequency=frequency)
                    except Exception as e:
                        err = str(e) or e.__class__.__name__
                        self._set_learning_state("active_learning", mode="rf", phase="rf_sweep", attempts=attempt + 1, last_error=err)

                if not frequency_found:
                    self._set_learning_state("error", mode="rf", phase="rf_sweep_timeout", error_msg="Timeout: No se pudo bloquear la frecuencia RF.")
                    await self._cancel_device_learning(ip)
                    return

                _LOGGER.info(f"Frecuencia RF bloqueada en {frequency} MHz. Esperando paquete de datos...")
                self._set_learning_state(
                    "active_learning_rf_packet",
                    mode="rf",
                    phase="rf_packet_waiting",
                    attempts=0,
                    frequency=frequency,
                    last_error=None
                )

                await asyncio.to_thread(dev.find_rf_packet, frequency)

                for attempt in range(90):
                    await asyncio.sleep(0.5)
                    try:
                        data = await asyncio.to_thread(dev.check_data)
                        if data:
                            b64_data = base64.b64encode(data).decode('utf-8')
                            self._set_learning_state(
                                "captured",
                                mode="rf",
                                phase="captured",
                                captured_data=b64_data,
                                error_msg=None,
                                attempts=attempt + 1,
                                last_error=None,
                                frequency=frequency
                            )
                            _LOGGER.info(f"Paquete RF capturado exitosamente ({len(data)} bytes).")
                            return
                    except Exception as e:
                        err = str(e) or e.__class__.__name__
                        self._set_learning_state(
                            "active_learning_rf_packet",
                            mode="rf",
                            phase="rf_packet_waiting",
                            attempts=attempt + 1,
                            last_error=err,
                            frequency=frequency
                        )

                self._set_learning_state("error", mode="rf", phase="rf_packet_timeout", error_msg="Timeout: No se pudo capturar el paquete RF.")
                await self._cancel_device_learning(ip)

            elif mode.startswith("rf_"):
                freq_val = 433.92 if "433" in mode else 315.0
                _LOGGER.info(f"Bypassing barrido RF, forzando frecuencia {freq_val} MHz en {ip}")

                await asyncio.to_thread(dev.auth)
                self._set_learning_state(
                    "active_learning_rf_packet",
                    mode="rf",
                    phase="rf_packet_waiting",
                    attempts=0,
                    frequency=freq_val,
                    last_error=None
                )

                await asyncio.to_thread(dev.find_rf_packet, freq_val)

                for attempt in range(90):
                    await asyncio.sleep(0.5)
                    try:
                        data = await asyncio.to_thread(dev.check_data)
                        if data:
                            b64_data = base64.b64encode(data).decode('utf-8')
                            self._set_learning_state(
                                "captured",
                                mode="rf",
                                phase="captured",
                                captured_data=b64_data,
                                error_msg=None,
                                attempts=attempt + 1,
                                last_error=None,
                                frequency=freq_val
                            )
                            _LOGGER.info(f"Paquete RF capturado en frecuencia forzada {freq_val} MHz ({len(data)} bytes).")
                            return
                    except Exception as e:
                        err = str(e) or e.__class__.__name__
                        self._set_learning_state(
                            "active_learning_rf_packet",
                            mode="rf",
                            phase="rf_packet_waiting",
                            attempts=attempt + 1,
                            last_error=err,
                            frequency=freq_val
                        )

                self._set_learning_state("error", mode="rf", phase="rf_packet_timeout", error_msg=f"Timeout: No se capturó paquete RF en {freq_val} MHz.")
                await self._cancel_device_learning(ip)

            else:
                self._set_learning_state("error", error_msg=f"Modo de aprendizaje no soportado: {mode}")
                await self._cancel_device_learning(ip)
        except Exception as e:
            _LOGGER.error(f"Error en bucle de aprendizaje Broadlink: {e}")
            self._set_learning_state("error", error_msg=str(e), last_error=str(e))
            await self._cancel_device_learning(ip)

    def save_remote(self, name: str, ip: str, remote_type: str, commands: Dict[str, str], domain: str = "switch", device_type: str = "custom") -> Dict[str, Any]:
        remote_data = {
            "name": name,
            "ip": ip,
            "type": remote_type,
            "commands": commands,
            "domain": domain,
            "device_type": device_type,
            "updated_at": time.time()
        }
        self.remotes[name] = remote_data
        self._save_remotes()
        # Register entities in Home Assistant
        self.sync_all_ha_entities()
        return remote_data

    def delete_remote(self, name: str) -> bool:
        if name in self.remotes:
            del self.remotes[name]
            self._save_remotes()
            self.sync_all_ha_entities()
            return True
        return False

    async def send_command(self, ip: str, b64_data: str) -> bool:
        try:
            data = base64.b64decode(b64_data)
            devices = await asyncio.to_thread(broadlink.discover, timeout=2)
            dev = None
            for d in devices:
                if d.host[0] == ip:
                    dev = d
                    break

            if not dev:
                _LOGGER.error(f"Broadlink device at IP {ip} not found for sending command.")
                return False

            await asyncio.to_thread(dev.auth)
            await asyncio.to_thread(dev.send_data, data)
            _LOGGER.info(f"Comando Broadlink enviado exitosamente a {ip}")
            return True
        except Exception as e:
            _LOGGER.error(f"Error al enviar comando Broadlink a {ip}: {e}")
            return False
