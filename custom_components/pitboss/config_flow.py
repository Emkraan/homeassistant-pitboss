"""Config flow for the PitBoss integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
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
from .coordinator import is_auth_error
from .pytboss.api import PitBoss
from .pytboss.ble import SERVICE_RPC, BleConnection
from .pytboss.exceptions import GrillUnavailable, RPCError
from .pytboss.grills import get_grills
from .pytboss.wss import WebSocketConnection

_LOGGER = logging.getLogger(__name__)


_PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def async_validate(hass: HomeAssistant, data: dict[str, Any]) -> str | None:
    """Connect to the grill and run an authenticated read.

    Returns an error key for the form, or None when the grill accepted the
    password.
    """
    if data[CONF_PROTOCOL] == PROTOCOL_WSS:
        conn = WebSocketConnection(data[CONF_GRILL_ID])
    else:
        device = bluetooth.async_ble_device_from_address(
            hass, data[CONF_ADDRESS], connectable=True
        )
        if device is None:
            return "cannot_connect"
        conn = BleConnection(device)
    api = PitBoss(conn, data[CONF_GRILL_MODEL], data.get(CONF_PASSWORD, ""))
    try:
        await api.start()
        await api.get_state()
    except GrillUnavailable:
        return "cannot_connect"
    except RPCError as ex:
        if is_auth_error(ex):
            return "invalid_auth"
        _LOGGER.debug("Validation RPC failed: %s", ex)
        return "cannot_connect"
    except TimeoutError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error validating the grill")
        return "unknown"
    finally:
        try:
            await api.stop()
        except Exception:  # noqa: BLE001
            pass
    return None


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
        """Handle user-initiated setup: choose WiFi or BLE."""
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
                                    label="WiFi (WebSocket), preferred",
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
        """Collect the grill password and check it against the grill."""
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input.get(CONF_PASSWORD, "")
            error = await async_validate(self.hass, self._entry_data(password))
            if error is None:
                return self._create_entry(password)
            errors["base"] = error

        return self.async_show_form(
            step_id="password",
            errors=errors,
            data_schema=vol.Schema(
                {vol.Optional(CONF_PASSWORD, default=""): _PASSWORD_SELECTOR}
            ),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """The grill rejected the stored password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_password_update("reauth_confirm", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_password_update("reconfigure", user_input)

    async def _async_password_update(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        entry = (
            self._get_reauth_entry()
            if step_id == "reauth_confirm"
            else self._get_reconfigure_entry()
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input.get(CONF_PASSWORD, "")}
            error = await async_validate(self.hass, data)
            if error is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error
        return self.async_show_form(
            step_id=step_id,
            errors=errors,
            data_schema=vol.Schema(
                {vol.Optional(CONF_PASSWORD, default=""): _PASSWORD_SELECTOR}
            ),
            description_placeholders={"grill": entry.title},
        )

    def _create_entry(self, password: str) -> ConfigFlowResult:
        title = self._grill_model or "PitBoss Grill"
        return self.async_create_entry(title=title, data=self._entry_data(password))

    def _entry_data(self, password: str) -> dict[str, Any]:
        data: dict[str, Any] = {
            CONF_PROTOCOL: self._protocol,
            CONF_GRILL_MODEL: self._grill_model,
            CONF_PASSWORD: password,
        }
        if self._protocol == PROTOCOL_WSS:
            data[CONF_GRILL_ID] = self._grill_id
        else:
            data[CONF_ADDRESS] = self._ble_address
        return data
