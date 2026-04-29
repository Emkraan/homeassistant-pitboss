"""Switch platform for PitBoss grills."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossCoordinator
from .entity import PitBossEntity
from .pytboss.grills import StateDict

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PitBossSwitchDescription(SwitchEntityDescription):
    """Describes a PitBoss switch."""

    is_on_fn: Callable[[StateDict], bool] = lambda _: False
    turn_on_fn: Callable[..., Coroutine[Any, Any, Any]] | None = None
    turn_off_fn: Callable[..., Coroutine[Any, Any, Any]] | None = None
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

    descriptions = []

    if "turn-primer-motor-on" in api.spec.control_board.commands:
        descriptions.append(
            PitBossSwitchDescription(
                key="primer_motor",
                translation_key="primer_motor",
                is_on_fn=lambda d: d.get("primeState", False),
                turn_on_fn=lambda: api.turn_primer_motor_on(),
                turn_off_fn=lambda: api.turn_primer_motor_off(),
            )
        )

    async_add_entities(PitBossSwitch(coordinator, desc) for desc in descriptions)


class PitBossSwitch(PitBossEntity, SwitchEntity):
    """A PitBoss switch entity."""

    entity_description: PitBossSwitchDescription

    def __init__(
        self,
        coordinator: PitBossCoordinator,
        description: PitBossSwitchDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.entity_description.available_fn(self.coordinator.data)

    @property
    def is_on(self) -> bool:
        if self.coordinator.data is None:
            return False
        return self.entity_description.is_on_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.entity_description.turn_on_fn:
            try:
                await self.entity_description.turn_on_fn()
            except Exception as ex:
                _LOGGER.error(
                    "Failed to turn on %s: %s", self.entity_description.key, ex
                )

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.entity_description.turn_off_fn:
            try:
                await self.entity_description.turn_off_fn()
            except Exception as ex:
                _LOGGER.error(
                    "Failed to turn off %s: %s", self.entity_description.key, ex
                )
