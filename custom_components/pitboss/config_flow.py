"""Config flow for the PitBoss integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_ADDRESS,
    CONF_GRILL_ID,
    CONF_GRILL_MODEL,
    CONF_PASSWORD,
    CONF_PROTOCOL,
    DOMAIN,
    PROTOCOL_BLE,
    PROTOCOL_WSS,
)
from .pytboss.ble import SERVICE_RPC
from .pytboss.grills import get_grills

_LOGGER = logging.getLogger(__name__)


def _grill_model_options() -> list[SelectOptionDict]:
    models = sorted(g.name for g in get_grills())
    return [SelectOptionDict(value=m, label=m) for m in models]


class PitBossConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PitBoss."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_devices: dict[str, str] = {}
        self._ble_address: str | None = None
        self._grill_id: str | None = None
        self._grill_model: str | None = None
        self._protocol: str = PROTOCOL_WSS

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle BLE discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._ble_address = discovery_info.address
        self._protocol = PROTOCOL_BLE
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_model()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user-initiated setup — choose WiFi or BLE."""
        if user_input is not None:
            self._protocol = user_input[CONF_PROTOCOL]
            if self._protocol == PROTOCOL_WSS:
                return await self.async_step_wifi()
            return await self.async_step_ble_pick()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROTOCOL, default=PROTOCOL_WSS): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=PROTOCOL_WSS,
                                    label="WiFi (WebSocket) — preferred",
                                ),
                                SelectOptionDict(
                                    value=PROTOCOL_BLE, label="Bluetooth LE"
                                ),
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_wifi(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the grill ID (device name) for WiFi connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            grill_id = user_input[CONF_GRILL_ID].strip()
            await self.async_set_unique_id(f"wss_{grill_id}")
            self._abort_if_unique_id_configured()
            self._grill_id = grill_id
            self._grill_model = user_input[CONF_GRILL_MODEL]
            return await self.async_step_password()

        return self.async_show_form(
            step_id="wifi",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GRILL_ID): str,
                    vol.Required(CONF_GRILL_MODEL): SelectSelector(
                        SelectSelectorConfig(
                            options=_grill_model_options(),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={
                "help": "Find your grill ID in the PitBoss app under device settings. It looks like 'PBL-MyGrillName'."
            },
        )

    async def async_step_ble_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick from discovered BLE devices."""
        if user_input is not None:
            self._ble_address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(self._ble_address)
            self._abort_if_unique_id_configured()
            return await self.async_step_model()

        current_addresses = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current_addresses:
                continue
            if SERVICE_RPC in info.service_uuids:
                self._discovered_devices[info.address] = info.name or info.address

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="ble_pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=addr, label=name)
                                for addr, name in self._discovered_devices.items()
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the grill model."""
        if user_input is not None:
            self._grill_model = user_input[CONF_GRILL_MODEL]
            return await self.async_step_password()

        return self.async_show_form(
            step_id="model",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GRILL_MODEL): SelectSelector(
                        SelectSelectorConfig(
                            options=_grill_model_options(),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_password(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Optionally collect the grill password."""
        if user_input is not None:
            return self._create_entry(user_input.get(CONF_PASSWORD, ""))

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema({vol.Optional(CONF_PASSWORD, default=""): str}),
            description_placeholders={
                "help": "Leave blank if your grill has no password set."
            },
        )

    def _create_entry(self, password: str) -> ConfigFlowResult:
        data: dict[str, Any] = {
            CONF_PROTOCOL: self._protocol,
            CONF_GRILL_MODEL: self._grill_model,
            CONF_PASSWORD: password,
        }
        if self._protocol == PROTOCOL_WSS:
            data[CONF_GRILL_ID] = self._grill_id
        else:
            data[CONF_ADDRESS] = self._ble_address

        title = self._grill_model or "PitBoss Grill"
        return self.async_create_entry(title=title, data=data)
