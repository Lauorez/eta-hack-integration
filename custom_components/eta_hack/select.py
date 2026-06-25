from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VarInfo
from .const import DOMAIN
from .coordinator import EtaHackCoordinator
from .entity import EtaHackEntity


def _is_select(info: VarInfo) -> bool:
    if not info.is_writable or info.type_ != "TEXT":
        return False
    str_values = {sv.lower() for sv, _ in info.valid_values}
    is_on_off = {"on", "off"} == str_values or {"ein", "aus"} == str_values
    return not is_on_off and len(info.valid_values) >= 2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EtaHackCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EtaHackSelect(coordinator, entry, item.uri, item.path)
        for item in coordinator.menu_items
        if item.uri in coordinator.var_info_cache
        and _is_select(coordinator.var_info_cache[item.uri])
    ]
    async_add_entities(entities)


class EtaHackSelect(EtaHackEntity, SelectEntity):
    def __init__(self, coordinator, entry, uri, path):
        info = coordinator.var_info_cache[uri]
        super().__init__(coordinator, entry, uri, path)
        self._valid_values = info.valid_values
        self._attr_options = [sv for sv, _ in info.valid_values]

    @property
    def current_option(self) -> str | None:
        var_data = self.coordinator.data.get("vars", {}).get(self._uri)
        if var_data is None:
            return None
        return var_data.str_value

    async def async_select_option(self, option: str) -> None:
        raw = next((r for sv, r in self._valid_values if sv == option), None)
        if raw is None:
            return
        await self.coordinator.client.set_var(self._uri, raw)
        await self.coordinator.async_request_refresh()
