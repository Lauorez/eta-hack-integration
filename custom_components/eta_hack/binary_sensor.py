from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EtaHackCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EtaHackCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EtaHackErrorSensor(coordinator, entry)])


class EtaHackErrorSensor(CoordinatorEntity[EtaHackCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Active Errors"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator: EtaHackCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_errors"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ETA",
        )

    @property
    def is_on(self) -> bool:
        errors = self.coordinator.data.get("errors", []) if self.coordinator.data else []
        return len(errors) > 0

    @property
    def extra_state_attributes(self) -> dict:
        errors = self.coordinator.data.get("errors", []) if self.coordinator.data else []
        return {
            "errors": [
                {
                    "msg": e.msg,
                    "priority": e.priority,
                    "time": e.time,
                    "description": e.description,
                }
                for e in errors
            ]
        }
