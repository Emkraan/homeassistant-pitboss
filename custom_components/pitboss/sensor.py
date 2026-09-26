"""Sensor platform for PitBoss grills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AT_TEMP_TOLERANCE, DOMAIN
from .coordinator import PitBossCoordinator
from .entity import PitBossEntity
from .pytboss.grills import StateDict

ERROR_KEYS = (
    "err1",
    "err2",
    "err3",
    "highTempErr",
    "fanErr",
    "hotErr",
    "motorErr",
    "erL",
)

STATUS_OPTIONS = ["off", "igniting", "preheating", "at_temperature", "cooling", "error"]


def grill_status(d: StateDict) -> str:
    """Derive a single human-readable status from the raw flags."""
    if not d.get("moduleIsOn"):
        return "off"
    if any(d.get(k) for k in ERROR_KEYS):
        return "error"
    temp, target = d.get("grillTemp"), d.get("grillSetTemp")
    if d.get("hotState"):
        return "igniting"
    if temp is None or target is None:
        return "preheating"
    if temp < target - AT_TEMP_TOLERANCE:
        return "preheating"
    if temp > target + AT_TEMP_TOLERANCE * 2:
        return "cooling"
    return "at_temperature"


@dataclass(frozen=True, kw_only=True)
class PitBossSensorDescription(SensorEntityDescription):
    """Describes a PitBoss sensor."""

    value_fn: Callable[[StateDict], float | int | str | None]
    available_fn: Callable[[StateDict], bool] = lambda _: True


def _temp(key: str, source: str, **kw) -> PitBossSensorDescription:
    return PitBossSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.get(source),
        available_fn=kw.pop("available_fn", lambda d: d.get(source) is not None),
        **kw,
    )


_on = lambda d: d.get("moduleIsOn", False) is True  # noqa: E731

BASE_SENSORS: tuple[PitBossSensorDescription, ...] = (
    PitBossSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUS_OPTIONS,
        value_fn=grill_status,
    ),
    _temp("grill_temp", "grillTemp", available_fn=_on),
    _temp("grill_set_temp", "grillSetTemp", available_fn=_on),
    _temp("smoker_temp", "smokerActTemp", entity_registry_enabled_default=False),
    PitBossSensorDescription(
        key="recipe_step",
        translation_key="recipe_step",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("recipeStep"),
        available_fn=_on,
    ),
    PitBossSensorDescription(
        key="recipe_time",
        translation_key="recipe_time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("recipeTime"),
        available_fn=_on,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PitBossCoordinator = hass.data[DOMAIN][entry.entry_id]
    probes = max(coordinator.api.spec.meat_probes or 0, 1)
    descriptions = list(BASE_SENSORS)
    for n in range(1, 5):
        # Probes beyond what the model ships with are disabled by default.
        descriptions.append(
            _temp(
                f"probe{n}_temp",
                f"p{n}Temp",
                entity_registry_enabled_default=n <= probes,
            )
        )
    async_add_entities(PitBossSensor(coordinator, desc) for desc in descriptions)


class PitBossSensor(PitBossEntity, SensorEntity):
    """A PitBoss sensor entity."""

    entity_description: PitBossSensorDescription

    def __init__(
        self, coordinator: PitBossCoordinator, description: PitBossSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.entity_description.available_fn(self.coordinator.data)

    @property
    def native_value(self) -> float | int | str | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.device_class == SensorDeviceClass.TEMPERATURE:
            if (self.coordinator.data or {}).get("isFahrenheit", True) is False:
                return UnitOfTemperature.CELSIUS
            return UnitOfTemperature.FAHRENHEIT
        return self.entity_description.native_unit_of_measurement
