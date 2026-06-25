from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EtaHackCoordinator
from .entity import EtaHackEntity
from .api import VarInfo


def _is_sensor(info: VarInfo) -> bool:
    if not info.is_writable:
        return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EtaHackCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EtaHackSensor(coordinator, entry, item.uri, item.path)
        for item in coordinator.menu_items
        if item.uri in coordinator.var_info_cache
        and _is_sensor(coordinator.var_info_cache[item.uri])
    ]
    async_add_entities(entities)


class EtaHackSensor(EtaHackEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, uri, path):
        info = coordinator.var_info_cache[uri]
        super().__init__(coordinator, entry, uri, path)
        self._dec_places = info.dec_places
        self._scale_factor = info.scale_factor
        self._attr_native_unit_of_measurement = info.unit or None

    @property
    def native_value(self):
        var_data = self.coordinator.data.get("vars", {}).get(self._uri)
        if var_data is None:
            return None
        sf = self._scale_factor or 1
        raw = var_data.raw
        value = raw / sf
        if self._dec_places == 0:
            return int(value)
        return round(value, self._dec_places)
