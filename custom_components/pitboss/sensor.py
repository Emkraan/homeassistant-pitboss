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
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossCoordinator
from .entity import PitBossEntity
from .pytboss.grills import StateDict


@dataclass(frozen=True)
class PitBossSensorDescription(SensorEntityDescription):
    """Describes a PitBoss sensor."""

    value_fn: Callable[[StateDict], float | int | str | None] = lambda _: None
    available_fn: Callable[[StateDict], bool] = lambda _: True


def _temp_unit(data: StateDict) -> str:
    return (
        UnitOfTemperature.FAHRENHEIT
        if data.get("isFahrenheit", True)
        else UnitOfTemperature.CELSIUS
    )


SENSOR_DESCRIPTIONS: tuple[PitBossSensorDescription, ...] = (
    PitBossSensorDescription(
        key="grill_temp",
        translation_key="grill_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("grillTemp"),
        available_fn=lambda d: d.get("moduleIsOn", False) is True,
    ),
    PitBossSensorDescription(
        key="grill_set_temp",
        translation_key="grill_set_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("grillSetTemp"),
        available_fn=lambda d: d.get("moduleIsOn", False) is True,
    ),
    PitBossSensorDescription(
        key="smoker_temp",
        translation_key="smoker_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("smokerActTemp"),
        available_fn=lambda d: d.get("moduleIsOn", False) is True,
    ),
    PitBossSensorDescription(
        key="probe1_temp",
        translation_key="probe1_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("p1Temp"),
        available_fn=lambda d: d.get("p1Temp") is not None,
    ),
    PitBossSensorDescription(
        key="probe2_temp",
        translation_key="probe2_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("p2Temp"),
        available_fn=lambda d: d.get("p2Temp") is not None,
    ),
    PitBossSensorDescription(
        key="probe3_temp",
        translation_key="probe3_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("p3Temp"),
        available_fn=lambda d: d.get("p3Temp") is not None,
    ),
    PitBossSensorDescription(
        key="probe4_temp",
        translation_key="probe4_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("p4Temp"),
        available_fn=lambda d: d.get("p4Temp") is not None,
    ),
    PitBossSensorDescription(
        key="probe1_target",
        translation_key="probe1_target",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("p1Target"),
        available_fn=lambda d: d.get("p1Target") is not None,
    ),
    PitBossSensorDescription(
        key="probe2_target",
        translation_key="probe2_target",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("p2Target"),
        available_fn=lambda d: d.get("p2Target") is not None,
    ),
    PitBossSensorDescription(
        key="recipe_step",
        translation_key="recipe_step",
        value_fn=lambda d: d.get("recipeStep"),
        available_fn=lambda d: d.get("moduleIsOn", False) is True,
    ),
    PitBossSensorDescription(
        key="recipe_time",
        translation_key="recipe_time",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda d: d.get("recipeTime"),
        available_fn=lambda d: d.get("moduleIsOn", False) is True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PitBossCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(PitBossSensor(coordinator, desc) for desc in SENSOR_DESCRIPTIONS)


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
            return _temp_unit(self.coordinator.data)
        return self.entity_description.native_unit_of_measurement
