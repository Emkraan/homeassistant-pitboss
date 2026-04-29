"""Binary sensor platform for PitBoss grills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossCoordinator
from .entity import PitBossEntity
from .pytboss.grills import StateDict


@dataclass(frozen=True)
class PitBossBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a PitBoss binary sensor."""

    value_fn: Callable[[StateDict], bool | None] = lambda _: None


BINARY_SENSOR_DESCRIPTIONS: tuple[PitBossBinarySensorDescription, ...] = (
    PitBossBinarySensorDescription(
        key="module_on",
        translation_key="module_on",
        value_fn=lambda d: d.get("moduleIsOn", False),
    ),
    PitBossBinarySensorDescription(
        key="fan_state",
        translation_key="fan_state",
        entity_category=None,
        value_fn=lambda d: d.get("fanState", False),
    ),
    PitBossBinarySensorDescription(
        key="igniter_state",
        translation_key="igniter_state",
        value_fn=lambda d: d.get("hotState", False),
    ),
    PitBossBinarySensorDescription(
        key="auger_state",
        translation_key="auger_state",
        value_fn=lambda d: d.get("motorState", False),
    ),
    PitBossBinarySensorDescription(
        key="err_probe1",
        translation_key="err_probe1",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("err1", False),
    ),
    PitBossBinarySensorDescription(
        key="err_probe2",
        translation_key="err_probe2",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("err2", False),
    ),
    PitBossBinarySensorDescription(
        key="err_probe3",
        translation_key="err_probe3",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("err3", False),
    ),
    PitBossBinarySensorDescription(
        key="err_high_temp",
        translation_key="err_high_temp",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("highTempErr", False),
    ),
    PitBossBinarySensorDescription(
        key="err_fan",
        translation_key="err_fan",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("fanErr", False),
    ),
    PitBossBinarySensorDescription(
        key="err_igniter",
        translation_key="err_igniter",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("hotErr", False),
    ),
    PitBossBinarySensorDescription(
        key="err_auger",
        translation_key="err_auger",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("motorErr", False),
    ),
    PitBossBinarySensorDescription(
        key="no_pellets",
        translation_key="no_pellets",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("noPellets", False),
    ),
    PitBossBinarySensorDescription(
        key="err_startup",
        translation_key="err_startup",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("erL", False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PitBossCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PitBossBinarySensor(coordinator, desc) for desc in BINARY_SENSOR_DESCRIPTIONS
    )


class PitBossBinarySensor(PitBossEntity, BinarySensorEntity):
    """A PitBoss binary sensor entity."""

    entity_description: PitBossBinarySensorDescription

    def __init__(
        self,
        coordinator: PitBossCoordinator,
        description: PitBossBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
