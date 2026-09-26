"""Diagnostics support for PitBoss."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, DOMAIN
from .coordinator import PitBossCoordinator

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: PitBossCoordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "password_set": bool(entry.data.get(CONF_PASSWORD)),
        "auth_ok": coordinator.auth_ok,
        "connected": bool(api and api.is_connected()),
        "firmware_version": coordinator.firmware_version,
        "spec": (
            {
                "name": api.spec.name,
                "min_temp": api.spec.min_temp,
                "max_temp": api.spec.max_temp,
                "meat_probes": api.spec.meat_probes,
                "has_lights": api.spec.has_lights,
                "commands": sorted(api.spec.control_board.commands),
            }
            if api
            else None
        ),
        "state": coordinator.data,
    }
