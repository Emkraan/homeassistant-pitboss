"""Base entity for the PitBoss integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PitBossCoordinator


class PitBossEntity(CoordinatorEntity[PitBossCoordinator]):
    """Base class for all PitBoss entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PitBossCoordinator, unique_suffix: str) -> None:
        super().__init__(coordinator)
        entry = coordinator._entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.api.spec.name if coordinator.api else entry.title,
            manufacturer="Dansons Inc.",
            model=entry.data.get("grill_model"),
        )

    @property
    def available(self) -> bool:
        """Entity is available only when the coordinator has fresh data and the API is connected."""
        if not super().available:
            return False
        if self.coordinator.api is None:
            return False
        if not self.coordinator.api.is_connected():
            return False
        if self.coordinator.data is None:
            return False
        return True
