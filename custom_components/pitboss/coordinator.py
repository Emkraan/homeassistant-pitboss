"""DataUpdateCoordinator for the PitBoss integration."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
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
    PROTOCOL_BLE,
    PROTOCOL_WSS,
)
from .pytboss.api import PitBoss
from .pytboss.ble import BleConnection
from .pytboss.exceptions import GrillUnavailable, NotConnectedError, RPCError
from .pytboss.grills import StateDict
from .pytboss.wss import WebSocketConnection

_LOGGER = logging.getLogger(__name__)

_DATA_STALENESS_THRESHOLD = 300


class PitBossCoordinator(DataUpdateCoordinator[StateDict]):
    """Coordinator that manages the PitBoss API connection and state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=PING_INTERVAL,
        )
        self._entry = entry
        self.api: PitBoss | None = None
        self._api_started = False
        self._last_data_ts: datetime | None = None
        self._protocol = entry.data[CONF_PROTOCOL]

    async def _async_setup(self) -> None:
        """Set up the API connection. Called once on integration load."""
        try:
            await self._start_api()
        except GrillUnavailable as ex:
            raise ConfigEntryNotReady(f"Grill unavailable: {ex}") from ex

    async def _start_api(self) -> None:
        grill_model = self._entry.data[CONF_GRILL_MODEL]
        password = self._entry.data.get(CONF_PASSWORD, "")

        if self._protocol == PROTOCOL_WSS:
            grill_id = self._entry.data[CONF_GRILL_ID]
            conn = WebSocketConnection(grill_id)
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

        self.api = PitBoss(conn, grill_model, password)
        await self.api.subscribe_state(self._on_state_update)
        await self.api.start()
        self._api_started = True

        if self._protocol == PROTOCOL_WSS:
            try:
                await self.api.set_wifi_update_frequency(fast=5, slow=60)
                await self.api.wake_wifi()
            except Exception as ex:
                _LOGGER.warning("Failed to configure WiFi update frequency: %s", ex)

    @callback
    def _on_ble_disconnected(self, _client) -> None:
        _LOGGER.warning("BLE disconnected — entities will show unavailable.")
        self._api_started = False
        self.async_update_listeners()

    async def _on_state_update(self, state: StateDict) -> None:
        self._last_data_ts = datetime.now()
        self.async_set_updated_data(state)

    async def _async_update_data(self) -> StateDict:
        """Ping the grill to verify connection; fetch state if we have none."""
        if not self._api_started or self.api is None:
            try:
                await self._start_api()
            except GrillUnavailable as ex:
                raise UpdateFailed(f"Could not connect to grill: {ex}") from ex

        try:
            await self.api.ping(timeout=PING_TIMEOUT)
        except (NotConnectedError, RPCError, TimeoutError) as ex:
            self._api_started = False
            raise UpdateFailed(f"Grill ping failed: {ex}") from ex
        except Exception as ex:
            self._api_started = False
            raise UpdateFailed(f"Unexpected error pinging grill: {ex}") from ex

        if self.data is None:
            try:
                state = await self.api.get_state()
                self._last_data_ts = datetime.now()
                return state
            except Exception as ex:
                raise UpdateFailed(f"Failed to fetch initial state: {ex}") from ex

        if self._last_data_ts is not None:
            age = (datetime.now() - self._last_data_ts).total_seconds()
            if age > _DATA_STALENESS_THRESHOLD:
                _LOGGER.warning("Grill state is %.0fs old — fetching fresh state.", age)
                try:
                    state = await self.api.get_state()
                    self._last_data_ts = datetime.now()
                    return state
                except Exception as ex:
                    _LOGGER.warning("Failed to refresh stale state: %s", ex)

        return self.data

    async def async_shutdown(self) -> None:
        """Stop the coordinator and disconnect."""
        await super().async_shutdown()
        if self.api is not None:
            try:
                await self.api.stop()
            except Exception as ex:
                _LOGGER.debug("Error stopping API on shutdown: %s", ex)
