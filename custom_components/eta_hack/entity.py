from __future__ import annotations

import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EtaHackCoordinator


def _uri_to_slug(uri: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", uri.lower()).strip("_")


class EtaHackEntity(CoordinatorEntity[EtaHackCoordinator]):
    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: EtaHackCoordinator,
        entry: ConfigEntry,
        uri: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._uri = uri
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{_uri_to_slug(uri)}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ETA",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.track_uri(self._uri)

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.untrack_uri(self._uri)
        await super().async_will_remove_from_hass()
