"""Base entity for the PitBoss integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_GRILL_ID, DOMAIN
from .coordinator import PitBossCoordinator


class PitBossEntity(CoordinatorEntity[PitBossCoordinator]):
    """Base class for all PitBoss entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PitBossCoordinator, unique_suffix: str) -> None:
        super().__init__(coordinator)
        entry = coordinator._entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        model = entry.data.get("grill_model")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"PitBoss {model}" if model else entry.title,
            manufacturer="Dansons Inc.",
            model=model,
            serial_number=entry.data.get(CONF_GRILL_ID),
            sw_version=coordinator.firmware_version,
        )

    @property
    def available(self) -> bool:
        """Available only when connected and at least one state frame has arrived."""
        if not super().available:
            return False
        api = self.coordinator.api
        if api is None or not api.is_connected():
            return False
        return bool(self.coordinator.data)


class PitBossControlEntity(PitBossEntity):
    """An entity that sends commands, so it needs a working grill password."""

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.auth_ok is not False
