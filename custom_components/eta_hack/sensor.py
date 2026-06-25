from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .controls import controlled_uris
from .coordinator import EtaHackCoordinator
from .entity import EtaHackEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EtaHackCoordinator = hass.data[DOMAIN][entry.entry_id]

    # A variable is owned by switch/number/select only when varinfo confirms it
    # is writable, or when the user has defined a manual control for it.
    # Everything else becomes a sensor. This guarantees a sensor for every menu
    # leaf even if varinfo discovery is incomplete on the device.
    owned_uris = {
        uri for uri, info in coordinator.var_info_cache.items() if info.is_writable
    }
    owned_uris |= controlled_uris(entry)
    entities = [
        EtaHackSensor(coordinator, entry, item.uri, item.path)
        for item in coordinator.menu_items
        if item.uri not in owned_uris
    ]
    async_add_entities(entities)


class EtaHackSensor(EtaHackEntity, SensorEntity):
    @property
    def _var(self):
        return self.coordinator.data.get("vars", {}).get(self._uri)

    @property
    def native_value(self):
        var = self._var
        if var is None:
            return None
        # Non-numeric / text variables: expose the formatted string.
        if var.str_value and not _looks_numeric(var.str_value):
            return var.str_value
        sf = var.scale_factor or 1
        value = var.raw / sf
        if var.dec_places == 0:
            return int(value)
        return round(value, var.dec_places)

    @property
    def native_unit_of_measurement(self):
        var = self._var
        if var is None or not var.unit:
            return None
        # Units only make sense for numeric states.
        if var.str_value and not _looks_numeric(var.str_value):
            return None
        return var.unit


def _looks_numeric(value: str) -> bool:
    try:
        float(value.replace(",", ".").split()[0])
        return True
    except (ValueError, IndexError):
        return False
