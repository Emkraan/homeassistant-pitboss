"""Client library for Mongoose OS configuration RPCs."""

from typing import Any

from .transport import Transport


class Config:
    """Client library for Mongoose OS configuration RPCs."""

    def __init__(self, conn: Transport) -> None:
        self._conn = conn

    async def get_info(self) -> dict:
        return await self._conn.send_command("Sys.GetInfo", {})

    async def get_config(self, key: str | None = None) -> dict:
        params = {}
        if key:
            params["key"] = key
        return await self._conn.send_command("Config.Get", params)

    async def save_config(self, reboot: bool = True):
        if reboot:
            await self._conn.send_command_without_answer(
                "Config.Save", {"reboot": reboot}
            )
        else:
            await self._conn.send_command("Config.Save", {"reboot": reboot})

    async def set(self, **kwargs):
        return await self._conn.send_command("Config.Set", {"config": kwargs})

    async def set_wifi_credentials(self, ssid: str, password: str) -> dict:
        return await self._conn.send_command("Config.Set", _wifi_params(ssid, password))

    async def set_wifi_ssid(self, ssid) -> dict:
        return await self._conn.send_command("Config.Set", _wifi_params(ssid=ssid))

    async def set_wifi_password(self, password) -> dict:
        return await self._conn.send_command(
            "Config.Set", _wifi_params(password=password)
        )


def _wifi_params(ssid: str | None = None, password: str | None = None) -> dict:
    sta: dict[str, Any] = {"enable": True}
    if ssid:
        sta["ssid"] = ssid
    if password:
        sta["pass"] = password
    return {"config": {"wifi": {"sta": sta}}}
