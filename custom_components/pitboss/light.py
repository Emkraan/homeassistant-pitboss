"""Light platform for PitBoss grills."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossCoordinator
from .entity import PitBossControlEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PitBossCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.api and coordinator.api.spec.has_lights:
        async_add_entities([GrillLight(coordinator)])


class GrillLight(PitBossControlEntity, LightEntity):
    """Light entity for the grill's built-in light."""

    _attr_translation_key = "grill_light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, coordinator: PitBossCoordinator) -> None:
        super().__init__(coordinator, "light")

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("lightState", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(
            self.coordinator.api.turn_light_on, optimistic={"lightState": True}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(
            self.coordinator.api.turn_light_off, optimistic={"lightState": False}
        )
