from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VarInfo
from .const import DOMAIN
from .coordinator import EtaHackCoordinator
from .entity import EtaHackEntity


def _is_number(info: VarInfo) -> bool:
    return info.is_writable and info.type_ != "TEXT"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EtaHackCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EtaHackNumber(coordinator, entry, item.uri, item.path)
        for item in coordinator.menu_items
        if item.uri in coordinator.var_info_cache
        and _is_number(coordinator.var_info_cache[item.uri])
    ]
    async_add_entities(entities)


class EtaHackNumber(EtaHackEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry, uri, path):
        info = coordinator.var_info_cache[uri]
        super().__init__(coordinator, entry, uri, path)
        self._scale_factor = info.scale_factor or 1
        self._dec_places = info.dec_places
        self._attr_native_unit_of_measurement = info.unit or None
        self._attr_native_step = round(1 / self._scale_factor, max(self._dec_places, 1))

    @property
    def native_value(self) -> float | None:
        var_data = self.coordinator.data.get("vars", {}).get(self._uri)
        if var_data is None:
            return None
        return round(var_data.raw / self._scale_factor, self._dec_places)

    async def async_set_native_value(self, value: float) -> None:
        raw = int(round(value * self._scale_factor))
        await self.coordinator.client.set_var(self._uri, raw)
        await self.coordinator.async_request_refresh()
