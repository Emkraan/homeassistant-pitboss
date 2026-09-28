"""DataUpdateCoordinator for the PitBoss integration."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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

    A grill that is powered off cannot be reached (and cannot be powered on
    remotely, by design). That is normal, not a failure: the coordinator
    marks the grill offline, entities go unavailable, and data resumes on its
    own once the grill is switched back on.
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
        # Whether the grill currently answers pings. False while powered off.
        self.online = False

    async def _async_setup(self) -> None:
        """Set up the API connection. Called once by the first refresh."""
        try:
            await self._start_api()
        except Exception as ex:  # noqa: BLE001
            # Grill is most likely powered off; retry on the next update.
            _LOGGER.debug("Grill not reachable at setup, will keep trying: %s", ex)
            await self._stop_api()

    def _set_offline(self, reason: BaseException) -> StateDict:
        """Mark the grill offline (normally: powered off) without failing the update."""
        if self.online:
            _LOGGER.info("Grill is offline (powered off or out of range): %s", reason)
        else:
            _LOGGER.debug("Grill still offline: %s", reason)
        self.online = False
        return self.data or {}

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
            self.firmware_version = (await api.get_firmware_version()).get("firmwareVersion")
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
        self.online = True
        self.async_set_updated_data(dict(state))

    async def _async_update_data(self) -> StateDict:
        """Ping the grill to verify the connection; fetch state if we have none."""
        if not self._api_started or self.api is None:
            try:
                await self._start_api()
            except Exception as ex:  # noqa: BLE001
                await self._stop_api()
                return self._set_offline(ex)

        try:
            await self.api.ping(timeout=PING_TIMEOUT)
        except Exception as ex:  # noqa: BLE001
            # The WebSocket transport reconnects on its own; only BLE needs a
            # fresh connection object.
            if self._protocol != PROTOCOL_WSS:
                self._api_started = False
            return self._set_offline(ex)

        if not self.online:
            _LOGGER.info("Grill is back online")
            self.online = True
            # Force a state refresh so entities recover without waiting for a push.
            self._last_data_ts = None

        stale = (
            self.data is None
            or self._last_data_ts is None
            or (datetime.now() - self._last_data_ts).total_seconds() > _DATA_STALENESS_THRESHOLD
        )
        if stale and self.auth_ok is not False:
            try:
                state = await self.api.get_state()
                self._last_data_ts = datetime.now()
                return {**(self.data or {}), **state}
            except Exception as ex:  # noqa: BLE001
                # Usually the grill is still booting; the next push or ping fixes it.
                _LOGGER.debug("State refresh failed: %s", ex)
        if self.data is None:
            # Password rejected and nothing pushed yet: wait for the next push.
            return {}
        if self._protocol == PROTOCOL_WSS and self.auth_ok and stale:
            with contextlib.suppress(Exception):
                await self.api.wake_wifi()
        return self.data

    async def async_command(
        self,
        call: Callable[[], Awaitable[Any]],
        optimistic: dict[str, Any] | None = None,
    ) -> None:
        """Run a grill command, turning failures into user-visible errors."""
        if self.api is None or not self.api.is_connected():
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_connected")
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
