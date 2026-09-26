"""DataUpdateCoordinator for the PitBoss integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ADDRESS,
    CONF_GRILL_ID,
    CONF_GRILL_MODEL,
    CONF_PASSWORD,
    CONF_PROTOCOL,
    DOMAIN,
    PING_INTERVAL,
    PING_TIMEOUT,
    PROTOCOL_WSS,
)
from .pytboss.api import PitBoss
from .pytboss.ble import BleConnection
from .pytboss.exceptions import GrillUnavailable, NotConnectedError, RPCError
from .pytboss.grills import StateDict
from .pytboss.wss import WebSocketConnection

_LOGGER = logging.getLogger(__name__)

_DATA_STALENESS_THRESHOLD = 300


def is_auth_error(ex: BaseException) -> bool:
    """Whether an RPC failed because the grill rejected the password."""
    return isinstance(ex, RPCError) and "unauthorized" in str(ex).lower()


class PitBossCoordinator(DataUpdateCoordinator[StateDict]):
    """Coordinator that manages the PitBoss API connection and state.

    State arrives by push (WebSocket status frames or BLE notifications).
    The periodic update only pings the grill so a dead link is noticed.
    Reading state never needs the grill password; commands do.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=PING_INTERVAL,
            config_entry=entry,
        )
        self._entry = entry
        self.api: PitBoss | None = None
        self._api_started = False
        self._last_data_ts: datetime | None = None
        self._protocol = entry.data[CONF_PROTOCOL]
        self.firmware_version: str | None = None
        # None = not checked yet, True = accepted, False = rejected.
        self.auth_ok: bool | None = None

    async def _async_setup(self) -> None:
        """Set up the API connection. Called once by the first refresh."""
        try:
            await self._start_api()
        except GrillUnavailable as ex:
            raise UpdateFailed(f"Grill unavailable: {ex}") from ex

    async def _start_api(self) -> None:
        await self._stop_api()
        grill_model = self._entry.data[CONF_GRILL_MODEL]
        password = self._entry.data.get(CONF_PASSWORD, "")

        if self._protocol == PROTOCOL_WSS:
            conn = WebSocketConnection(self._entry.data[CONF_GRILL_ID])
        else:
            address = self._entry.data[CONF_ADDRESS]
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, address, connectable=True
            )
            if ble_device is None:
                raise GrillUnavailable(f"BLE device {address} not found")
            conn = BleConnection(
                ble_device,
                disconnect_callback=self._on_ble_disconnected,
            )

        api = PitBoss(conn, grill_model, password)
        await api.subscribe_state(self._on_state_update)
        await api.start()
        self.api = api
        self._api_started = True

        try:
            self.firmware_version = (await api.get_firmware_version()).get(
                "firmwareVersion"
            )
        except Exception as ex:  # noqa: BLE001
            _LOGGER.debug("Could not read firmware version: %s", ex)

        await self._async_check_auth()

        if self._protocol == PROTOCOL_WSS and self.auth_ok:
            try:
                await api.set_wifi_update_frequency(fast=5, slow=60)
                await api.wake_wifi()
            except Exception as ex:  # noqa: BLE001
                _LOGGER.debug("Failed to configure WiFi update frequency: %s", ex)

    async def _async_check_auth(self) -> None:
        """Probe the password with an authenticated read and start reauth if rejected."""
        if self.api is None:
            return
        try:
            state = await self.api.get_state()
        except RPCError as ex:
            if is_auth_error(ex):
                self.auth_ok = False
                _LOGGER.warning(
                    "The grill rejected the configured password. Monitoring still "
                    "works, but controls are disabled until the password is fixed "
                    "(Settings > Devices & services > PitBoss > Reconfigure)"
                )
                self._entry.async_start_reauth(self.hass)
                return
            _LOGGER.debug("Auth probe failed for a non-auth reason: %s", ex)
            return
        except Exception as ex:  # noqa: BLE001
            _LOGGER.debug("Auth probe failed: %s", ex)
            return
        self.auth_ok = True
        if state:
            self._last_data_ts = datetime.now()
            self.async_set_updated_data({**(self.data or {}), **state})

    async def _stop_api(self) -> None:
        if self.api is not None:
            try:
                await self.api.stop()
            except Exception as ex:  # noqa: BLE001
                _LOGGER.debug("Error stopping API: %s", ex)
        self.api = None
        self._api_started = False

    @callback
    def _on_ble_disconnected(self, _client) -> None:
        _LOGGER.warning("BLE disconnected, entities will show unavailable")
        self._api_started = False
        self.async_update_listeners()

    async def _on_state_update(self, state: StateDict) -> None:
        self._last_data_ts = datetime.now()
        self.async_set_updated_data(dict(state))

    async def _async_update_data(self) -> StateDict:
        """Ping the grill to verify the connection; fetch state if we have none."""
        if not self._api_started or self.api is None:
            try:
                await self._start_api()
            except GrillUnavailable as ex:
                raise UpdateFailed(f"Could not connect to grill: {ex}") from ex

        try:
            await self.api.ping(timeout=PING_TIMEOUT)
        except (NotConnectedError, RPCError, TimeoutError) as ex:
            # The WebSocket transport reconnects on its own; only BLE needs a
            # fresh connection object.
            if self._protocol != PROTOCOL_WSS:
                self._api_started = False
            raise UpdateFailed(f"Grill ping failed: {ex}") from ex
        except Exception as ex:
            if self._protocol != PROTOCOL_WSS:
                self._api_started = False
            raise UpdateFailed(f"Unexpected error pinging grill: {ex}") from ex

        stale = self.data is None or (
            self._last_data_ts is not None
            and (datetime.now() - self._last_data_ts).total_seconds()
            > _DATA_STALENESS_THRESHOLD
        )
        if stale and self.auth_ok is not False:
            try:
                state = await self.api.get_state()
                self._last_data_ts = datetime.now()
                return {**(self.data or {}), **state}
            except Exception as ex:  # noqa: BLE001
                if self.data is None and not is_auth_error(ex):
                    raise UpdateFailed(f"Failed to fetch state: {ex}") from ex
                _LOGGER.debug("State refresh failed: %s", ex)
        if self.data is None:
            # Password rejected and nothing pushed yet: wait for the next push.
            return {}
        if self._protocol == PROTOCOL_WSS and self.auth_ok and stale:
            try:
                await self.api.wake_wifi()
            except Exception:  # noqa: BLE001
                pass
        return self.data

    async def async_command(
        self,
        call: Callable[[], Awaitable[Any]],
        optimistic: dict[str, Any] | None = None,
    ) -> None:
        """Run a grill command, turning failures into user-visible errors."""
        if self.api is None or not self.api.is_connected():
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_connected"
            )
        try:
            await call()
        except RPCError as ex:
            if is_auth_error(ex):
                if self.auth_ok is not False:
                    self.auth_ok = False
                    self._entry.async_start_reauth(self.hass)
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="invalid_password"
                ) from ex
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(ex)},
            ) from ex
        except (NotConnectedError, TimeoutError) as ex:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_connected"
            ) from ex
        self.auth_ok = True
        if optimistic and self.data is not None:
            self.async_set_updated_data({**self.data, **optimistic})

    async def async_shutdown(self) -> None:
        """Stop the coordinator and disconnect."""
        await super().async_shutdown()
        await self._stop_api()
