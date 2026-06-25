from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VarInfo
from .const import DOMAIN
from .controls import get_controls
from .coordinator import EtaHackCoordinator
from .entity import EtaHackEntity, resolve_name


def _is_number(info: VarInfo) -> bool:
    return info.is_writable and info.type_ != "TEXT"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EtaHackCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[EtaHackNumber] = []

    # Auto-detected via varinfo (API >= 1.2)
    for item in coordinator.menu_items:
        info = coordinator.var_info_cache.get(item.uri)
        if info and _is_number(info):
            entities.append(EtaHackNumber(coordinator, entry, item.uri, item.path))

    # User-defined manual controls (works on any firmware)
    for control in get_controls(entry, "number"):
        name = resolve_name(coordinator, control["uri"], control.get("name", ""))
        entities.append(
            EtaHackNumber(
                coordinator,
                entry,
                control["uri"],
                name,
                min_value=control.get("min"),
                max_value=control.get("max"),
                step=control.get("step"),
            )
        )

    async_add_entities(entities)


class EtaHackNumber(EtaHackEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry, uri, name, min_value=None, max_value=None, step=None):
        super().__init__(coordinator, entry, uri, name)
        if min_value is not None:
            self._attr_native_min_value = float(min_value)
        if max_value is not None:
            self._attr_native_max_value = float(max_value)
        if step is not None:
            self._attr_native_step = float(step)

    def _scale_factor(self) -> int:
        info = self.coordinator.var_info_cache.get(self._uri)
        if info and info.scale_factor:
            return info.scale_factor
        var = self.coordinator.data.get("vars", {}).get(self._uri)
        if var and var.scale_factor:
            return var.scale_factor
        return 1

    def _dec_places(self) -> int:
        info = self.coordinator.var_info_cache.get(self._uri)
        if info:
            return info.dec_places
        var = self.coordinator.data.get("vars", {}).get(self._uri)
        return var.dec_places if var else 0

    @property
    def native_unit_of_measurement(self):
        info = self.coordinator.var_info_cache.get(self._uri)
        if info and info.unit:
            return info.unit
        var = self.coordinator.data.get("vars", {}).get(self._uri)
        return (var.unit if var else None) or None

    @property
    def native_value(self) -> float | None:
        var = self.coordinator.data.get("vars", {}).get(self._uri)
        if var is None:
            return None
        return round(var.raw / self._scale_factor(), self._dec_places())

    async def async_set_native_value(self, value: float) -> None:
        raw = int(round(value * self._scale_factor()))
        await self.coordinator.client.set_var(self._uri, raw)
        await self.coordinator.async_request_refresh()
