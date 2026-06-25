from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VarInfo
from .const import DOMAIN
from .controls import get_controls
from .coordinator import EtaHackCoordinator
from .entity import EtaHackEntity, resolve_name


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
    entities: list[EtaHackSelect] = []

    # Auto-detected via varinfo (API >= 1.2)
    for item in coordinator.menu_items:
        info = coordinator.var_info_cache.get(item.uri)
        if info and _is_select(info):
            entities.append(
                EtaHackSelect(coordinator, entry, item.uri, item.path, info.valid_values)
            )

    # User-defined manual controls (works on any firmware)
    for control in get_controls(entry, "select"):
        name = resolve_name(coordinator, control["uri"], control.get("name", ""))
        valid_values = [(label, raw) for label, raw in control["options"].items()]
        entities.append(EtaHackSelect(coordinator, entry, control["uri"], name, valid_values))

    async_add_entities(entities)


class EtaHackSelect(EtaHackEntity, SelectEntity):
    def __init__(self, coordinator, entry, uri, name, valid_values):
        super().__init__(coordinator, entry, uri, name)
        self._valid_values = list(valid_values)
        self._attr_options = [label for label, _ in self._valid_values]

    @property
    def current_option(self) -> str | None:
        var_data = self.coordinator.data.get("vars", {}).get(self._uri)
        if var_data is None:
            return None
        # Match the live raw value to a configured label.
        for label, raw in self._valid_values:
            if raw == var_data.raw:
                return label
        # Fall back to the device's formatted string if it matches an option.
        if var_data.str_value in self._attr_options:
            return var_data.str_value
        return None

    async def async_select_option(self, option: str) -> None:
        raw = next((r for label, r in self._valid_values if label == option), None)
        if raw is None:
            return
        await self.coordinator.client.set_var(self._uri, raw)
        await self.coordinator.async_request_refresh()
