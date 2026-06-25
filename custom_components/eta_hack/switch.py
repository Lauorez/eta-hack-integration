from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VarInfo
from .const import DOMAIN
from .controls import get_controls
from .coordinator import EtaHackCoordinator
from .entity import EtaHackEntity, resolve_name


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
    entities: list[EtaHackSwitch] = []

    # Auto-detected via varinfo (API >= 1.2)
    for item in coordinator.menu_items:
        info = coordinator.var_info_cache.get(item.uri)
        if info and _is_switch(info):
            on_raw = next(raw for sv, raw in info.valid_values if sv.lower() in ("on", "ein"))
            off_raw = next(raw for sv, raw in info.valid_values if sv.lower() in ("off", "aus"))
            entities.append(EtaHackSwitch(coordinator, entry, item.uri, item.path, on_raw, off_raw))

    # User-defined manual controls (works on any firmware)
    for control in get_controls(entry, "switch"):
        name = resolve_name(coordinator, control["uri"], control.get("name", ""))
        entities.append(
            EtaHackSwitch(coordinator, entry, control["uri"], name, control["on"], control["off"])
        )

    async_add_entities(entities)


class EtaHackSwitch(EtaHackEntity, SwitchEntity):
    def __init__(self, coordinator, entry, uri, name, on_raw, off_raw):
        super().__init__(coordinator, entry, uri, name)
        self._on_raw = on_raw
        self._off_raw = off_raw

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
