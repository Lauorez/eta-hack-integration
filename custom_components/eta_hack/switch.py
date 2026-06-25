from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VarInfo
from .const import DOMAIN
from .coordinator import EtaHackCoordinator
from .entity import EtaHackEntity


def _is_switch(info: VarInfo) -> bool:
    if not info.is_writable or info.type_ != "TEXT":
        return False
    if len(info.valid_values) != 2:
        return False
    str_values = {sv.lower() for sv, _ in info.valid_values}
    return {"on", "off"} == str_values or {"ein", "aus"} == str_values


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EtaHackCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EtaHackSwitch(coordinator, entry, item.uri, item.path)
        for item in coordinator.menu_items
        if item.uri in coordinator.var_info_cache
        and _is_switch(coordinator.var_info_cache[item.uri])
    ]
    async_add_entities(entities)


class EtaHackSwitch(EtaHackEntity, SwitchEntity):
    def __init__(self, coordinator, entry, uri, path):
        info = coordinator.var_info_cache[uri]
        super().__init__(coordinator, entry, uri, path)
        self._on_raw = next(
            raw for sv, raw in info.valid_values if sv.lower() in ("on", "ein")
        )
        self._off_raw = next(
            raw for sv, raw in info.valid_values if sv.lower() in ("off", "aus")
        )

    @property
    def is_on(self) -> bool | None:
        var_data = self.coordinator.data.get("vars", {}).get(self._uri)
        if var_data is None:
            return None
        return var_data.raw == self._on_raw

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.client.set_var(self._uri, self._on_raw)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.set_var(self._uri, self._off_raw)
        await self.coordinator.async_request_refresh()
