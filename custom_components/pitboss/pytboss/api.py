"""High-level API for interacting with PitBoss grills."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from time import time
from typing import Awaitable, Callable

from .codec import encode, timed_key
from .config import Config
from .exceptions import UnsupportedOperation
from .fs import FileSystem
from .grills import Grill, StateDict, get_grill
from .transport import Transport

_LOGGER = logging.getLogger(__name__)

_UPTIME_CACHE_TTL = 5
_DEFAULT_PING_TIMEOUT = 10.0

StateCallback = Callable[[StateDict], Awaitable[None] | None]
VDataCallback = Callable[[dict], Awaitable[None] | None]


class PitBoss:
    """API for interacting with PitBoss grills."""

    fs: FileSystem
    config: Config
    spec: Grill

    def __init__(self, conn: Transport, grill_model: str, password: str = "") -> None:
        self.fs = FileSystem(conn)
        self.config = Config(conn)
        self._grill_model = grill_model
        self._conn = conn
        self._conn.set_state_callback(self._on_state_received)
        self._conn.set_vdata_callback(self._on_vdata_received)
        self._password = password.encode("utf-8")
        self._lock = asyncio.Lock()
        self._state_callbacks: list[StateCallback] = []
        self._vdata_callbacks: list[VDataCallback] = []
        self._state = StateDict()
        self._last_uptime: float | None = None
        self._last_uptime_check: int | None = None
        self._uptime_lock = asyncio.Lock()

    def is_connected(self) -> bool:
        return self._conn.is_connected()

    async def start(self) -> None:
        self.spec = await asyncio.to_thread(get_grill, self._grill_model)
        await self._conn.connect()

    async def stop(self) -> None:
        await self._conn.disconnect()

    async def subscribe_state(self, callback: StateCallback) -> None:
        async with self._lock:
            self._state_callbacks.append(callback)

    async def subscribe_vdata(self, callback: VDataCallback) -> None:
        async with self._lock:
            self._vdata_callbacks.append(callback)

    async def _on_state_received(
        self,
        status_payload: str | None,
        temperatures_payload: str | None = None,
    ) -> None:
        _LOGGER.debug(
            "State received: status=%s, temperatures=%s",
            status_payload,
            temperatures_payload,
        )
        try:
            state = StateDict()
            if status_payload:
                if new_state := self.spec.control_board.parse_status(status_payload):
                    state.update(new_state)
            if temperatures_payload:
                if new_state := self.spec.control_board.parse_temperatures(
                    temperatures_payload
                ):
                    state.update(new_state)

            if not state:
                _LOGGER.debug("Could not parse state payload — ignoring")
                return

            async with self._lock:
                self._state.update(state)
                for callback in self._state_callbacks:
                    try:
                        if inspect.iscoroutinefunction(callback):
                            await callback(self._state)
                        else:
                            callback(self._state)
                    except Exception as ex:
                        _LOGGER.warning("State callback raised an exception: %s", ex)
        except Exception as ex:
            _LOGGER.warning("Error processing state payload: %s", ex, exc_info=True)

    async def _on_vdata_received(self, payload: str) -> None:
        try:
            vdata = json.loads(payload)
            _LOGGER.debug("VData received: %s", vdata)
            async with self._lock:
                for callback in self._vdata_callbacks:
                    try:
                        if inspect.iscoroutinefunction(callback):
                            await callback(vdata)
                        else:
                            callback(vdata)
                    except Exception as ex:
                        _LOGGER.warning("VData callback raised an exception: %s", ex)
        except Exception as ex:
            _LOGGER.warning("Error processing vdata payload: %s", ex, exc_info=True)

    async def _authenticate(self, params: dict) -> dict:
        if self._password:
            params["psw"] = encode(
                self._password, key=timed_key(await self.get_uptime())
            ).hex()
        return params

    async def _send_hex_command(self, cmd: str) -> dict:
        return await self._conn.send_command(
            "PB.SendMCUCommand", await self._authenticate({"command": cmd})
        )

    async def _send_command(self, slug: str, *args) -> dict:
        cmd = self.spec.control_board.commands[slug]
        return await self._send_hex_command(cmd(*args))

    async def set_grill_temperature(self, temp: int) -> dict:
        if self.spec.max_temp:
            temp = min(temp, self.spec.max_temp)
        if self.spec.min_temp:
            temp = max(temp, self.spec.min_temp)
        return await self._send_command("set-temperature", temp)

    async def set_probe_temperature(self, temp: int) -> dict:
        return await self._send_command("set-probe-1-temperature", temp)

    async def set_probe_2_temperature(self, temp: int) -> dict:
        cmd = "set-probe-2-temperature"
        if cmd not in self.spec.control_board.commands:
            raise UnsupportedOperation
        return await self._send_command(cmd, temp)

    async def turn_light_on(self) -> dict:
        if not self.spec.has_lights:
            return {}
        return await self._send_command("turn-light-on")

    async def turn_light_off(self) -> dict:
        if not self.spec.has_lights:
            return {}
        return await self._send_command("turn-light-off")

    async def turn_grill_off(self) -> dict:
        return await self._send_command("turn-off")

    async def turn_primer_motor_on(self) -> dict:
        return await self._send_command("turn-primer-motor-on")

    async def turn_primer_motor_off(self) -> dict:
        return await self._send_command("turn-primer-motor-off")

    async def get_state(self) -> StateDict:
        resp = await self._conn.send_command(
            "PB.GetState", await self._authenticate({})
        )
        status = self.spec.control_board.parse_status(resp.get("sc_11", "")) or {}
        status.update(
            self.spec.control_board.parse_temperatures(resp.get("sc_12", "")) or {}
        )
        return status

    async def get_firmware_version(self) -> dict:
        return await self._conn.send_command("PB.GetFirmwareVersion", {})

    async def set_mcu_update_timer(self, frequency: int = 2) -> dict:
        return await self._conn.send_command(
            "PB.SetMCU_UpdateFrequency", {"frequency": frequency}
        )

    async def set_wifi_update_frequency(self, fast: int = 5, slow: int = 60) -> dict:
        return await self._conn.send_command(
            "PB.SetWifiUpdateFrequency",
            await self._authenticate({"slow": slow, "fast": fast}),
        )

    async def wake_wifi(self) -> dict:
        """Triggers 5 minutes of fast (5s) WiFi state pushes."""
        return await self._conn.send_command(
            "PB.WiFiAwakeWDT", await self._authenticate({})
        )

    async def get_uptime(self) -> float:
        async with self._uptime_lock:
            now = int(time())
            if (
                not self._last_uptime_check
                or now - self._last_uptime_check > _UPTIME_CACHE_TTL
            ):
                result = await self._conn.send_command("PB.GetTime", {})
                self._last_uptime = result.get("time", 0.0)
                self._last_uptime_check = now
            return self._last_uptime or 0.0

    async def ping(self, timeout: float = _DEFAULT_PING_TIMEOUT) -> dict:
        return await self._conn.send_command("RPC.Ping", {}, timeout=timeout)

    async def set_grill_password(self, new_password: str) -> None:
        new_password_bytes = new_password.encode("utf-8")
        await self._conn.send_command(
            "PB.SetDevicePassword",
            await self._authenticate({"newPassword": encode(new_password_bytes).hex()}),
        )
        self._password = new_password_bytes
