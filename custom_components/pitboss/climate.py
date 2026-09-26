"""Climate platform for PitBoss grills."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossCoordinator
from .entity import PitBossEntity

_TEMP_STEP = 5.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PitBossCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GrillClimate(coordinator)])


class GrillClimate(PitBossEntity, ClimateEntity):
    """The grill's cooking chamber: current temperature, set point, and shutdown."""

    _attr_translation_key = "grill"
    _attr_name = None
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = _TEMP_STEP
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: PitBossCoordinator) -> None:
        super().__init__(coordinator, "climate")

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    @property
    def temperature_unit(self) -> str:
        if self._data.get("isFahrenheit", True) is False:
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self._data.get("moduleIsOn") else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        d = self._data
        if not d.get("moduleIsOn"):
            return HVACAction.OFF
        if d.get("hotState") or d.get("motorState"):
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        return self._data.get("grillTemp")

    @property
    def target_temperature(self) -> float | None:
        if not self._data.get("moduleIsOn"):
            return None
        return self._data.get("grillSetTemp")

    @property
    def min_temp(self) -> float:
        api = self.coordinator.api
        if api and api.spec.min_temp:
            return float(api.spec.min_temp)
        return 180.0

    @property
    def max_temp(self) -> float:
        api = self.coordinator.api
        if api and api.spec.max_temp:
            return float(api.spec.max_temp)
        return 500.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._data
        return {
            "probe_1_temperature": d.get("p1Temp"),
            "probe_1_target": d.get("p1Target"),
            "probe_2_temperature": d.get("p2Temp"),
            "pellets_low": d.get("noPellets"),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (mode := kwargs.get(ATTR_HVAC_MODE)) == HVACMode.OFF:
            await self.async_set_hvac_mode(mode)
            return
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        if not self._data.get("moduleIsOn"):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="grill_off"
            )
        target = int(round(temp / _TEMP_STEP) * _TEMP_STEP)
        target = max(int(self.min_temp), min(int(self.max_temp), target))
        await self.coordinator.async_command(
            lambda: self.coordinator.api.set_grill_temperature(target),
            optimistic={"grillSetTemp": target},
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_command(self.coordinator.api.turn_grill_off)
            return
        if not self._data.get("moduleIsOn"):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="power_on_unsupported"
            )

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
