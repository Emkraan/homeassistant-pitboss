"""Number platform for PitBoss grills — probe target temperatures."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Coroutine, Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MAX_PROBE_TEMP, MIN_PROBE_TEMP
from .coordinator import PitBossCoordinator
from .entity import PitBossEntity
from .pytboss.grills import StateDict

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PitBossNumberDescription(NumberEntityDescription):
    """Describes a PitBoss number entity."""

    value_fn: Callable[[StateDict], float | None] = lambda _: None
    set_fn: Callable[..., Coroutine[Any, Any, Any]] | None = None
    available_fn: Callable[[StateDict], bool] = (
        lambda d: d.get("moduleIsOn", False) is True
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PitBossCoordinator = hass.data[DOMAIN][entry.entry_id]
    api = coordinator.api
    commands = api.spec.control_board.commands

    descriptions = []

    if "set-probe-1-temperature" in commands:
        descriptions.append(
            PitBossNumberDescription(
                key="probe1_target",
                translation_key="probe1_target",
                device_class=NumberDeviceClass.TEMPERATURE,
                mode=NumberMode.BOX,
                native_min_value=MIN_PROBE_TEMP,
                native_max_value=MAX_PROBE_TEMP,
                native_step=1,
                value_fn=lambda d: d.get("p1Target"),
                set_fn=lambda v: api.set_probe_temperature(int(v)),
                available_fn=lambda d: (
                    d.get("moduleIsOn", False) is True and d.get("p1Temp") is not None
                ),
            )
        )

    if "set-probe-2-temperature" in commands:
        descriptions.append(
            PitBossNumberDescription(
                key="probe2_target",
                translation_key="probe2_target",
                device_class=NumberDeviceClass.TEMPERATURE,
                mode=NumberMode.BOX,
                native_min_value=MIN_PROBE_TEMP,
                native_max_value=MAX_PROBE_TEMP,
                native_step=1,
                value_fn=lambda d: d.get("p2Target"),
                set_fn=lambda v: api.set_probe_2_temperature(int(v)),
                available_fn=lambda d: (
                    d.get("moduleIsOn", False) is True and d.get("p2Temp") is not None
                ),
            )
        )

    async_add_entities(PitBossNumber(coordinator, desc) for desc in descriptions)


class PitBossNumber(PitBossEntity, NumberEntity):
    """A PitBoss number entity for probe target temperatures."""

    entity_description: PitBossNumberDescription

    def __init__(
        self,
        coordinator: PitBossCoordinator,
        description: PitBossNumberDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.entity_description.available_fn(self.coordinator.data)

    @property
    def native_unit_of_measurement(self) -> str:
        if self.coordinator.data and not self.coordinator.data.get(
            "isFahrenheit", True
        ):
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        if self.entity_description.set_fn:
            try:
                await self.entity_description.set_fn(value)
            except Exception as ex:
                _LOGGER.error(
                    "Failed to set %s to %s: %s", self.entity_description.key, value, ex
                )
