"""Climate platform for PitBoss grills."""

from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossCoordinator
from .entity import PitBossEntity

_LOGGER = logging.getLogger(__name__)

_TEMP_STEP = 5.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PitBossCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GrillClimate(coordinator)])


class GrillClimate(PitBossEntity, ClimateEntity):
    """Climate entity representing the grill's main cooking chamber."""

    _attr_translation_key = "grill"
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = _TEMP_STEP

    def __init__(self, coordinator: PitBossCoordinator) -> None:
        super().__init__(coordinator, "climate")

    @property
    def temperature_unit(self) -> str:
        if self.coordinator.data and not self.coordinator.data.get(
            "isFahrenheit", True
        ):
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def hvac_mode(self) -> HVACMode:
        if self.coordinator.data and self.coordinator.data.get("moduleIsOn"):
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        if self.coordinator.data:
            return self.coordinator.data.get("grillTemp")
        return None

    @property
    def target_temperature(self) -> float | None:
        if self.coordinator.data:
            return self.coordinator.data.get("grillSetTemp")
        return None

    @property
    def min_temp(self) -> float:
        if self.coordinator.api and self.coordinator.api.spec.min_temp:
            return float(self.coordinator.api.spec.min_temp)
        return 180.0

    @property
    def max_temp(self) -> float:
        if self.coordinator.api and self.coordinator.api.spec.max_temp:
            return float(self.coordinator.api.spec.max_temp)
        return 500.0

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        try:
            await self.coordinator.api.set_grill_temperature(int(temp))
        except Exception as ex:
            _LOGGER.error("Failed to set grill temperature: %s", ex)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            try:
                await self.coordinator.api.turn_grill_off()
            except Exception as ex:
                _LOGGER.error("Failed to turn grill off: %s", ex)
        else:
            _LOGGER.warning(
                "Remote power-on is not supported — use the physical controls."
            )
