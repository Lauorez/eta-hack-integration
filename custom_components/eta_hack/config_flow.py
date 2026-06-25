from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EtaApiError, EtaHackClient
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .controls import CONF_CONTROLS, get_controls

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=10, max=3600)
        ),
    }
)


class EtaHackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            session = async_get_clientsession(self.hass)
            client = EtaHackClient(session, host, port)
            try:
                await client.get_api_version()
            except EtaApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"ETA Hack ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EtaHackOptionsFlow()


class EtaHackOptionsFlow(config_entries.OptionsFlow):
    """Manage user-defined writable controls (needed on API < 1.2)."""

    def __init__(self) -> None:
        self._controls: list[dict] | None = None
        self._pending: dict = {}

    @property
    def controls(self) -> list[dict]:
        if self._controls is None:
            self._controls = get_controls(self.config_entry)
        return self._controls

    def _uri_selector(self) -> selector.SelectSelector:
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        options = [
            selector.SelectOptionDict(value=item.uri, label=f"{item.path} ({item.uri})")
            for item in coordinator.menu_items
        ]
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
                sort=True,
            )
        )

    async def _read_var(self, uri: str):
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        try:
            return await coordinator.client.get_var(uri)
        except EtaApiError:
            return None

    async def async_step_init(self, user_input=None):
        _ = self.controls  # ensure loaded
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_switch", "add_number", "add_select", "remove", "save"],
        )

    # --- Switch (two steps: pick variable, then confirm on/off raw values) ---
    async def async_step_add_switch(self, user_input=None):
        if user_input is not None:
            self._pending = {"uri": user_input["uri"], "name": user_input.get("name", "")}
            return await self.async_step_add_switch_values()
        return self.async_show_form(
            step_id="add_switch",
            data_schema=vol.Schema(
                {vol.Required("uri"): self._uri_selector(), vol.Optional("name", default=""): str}
            ),
        )

    async def async_step_add_switch_values(self, user_input=None):
        if user_input is not None:
            self.controls.append(
                {
                    "type": "switch",
                    "uri": self._pending["uri"],
                    "name": self._pending["name"],
                    "off": int(user_input["off"]),
                    "on": int(user_input["on"]),
                }
            )
            return await self.async_step_init()

        var = await self._read_var(self._pending["uri"])
        default_off = var.adv_text_offset if var else 0
        default_on = (var.adv_text_offset + 1) if var else 1
        return self.async_show_form(
            step_id="add_switch_values",
            data_schema=vol.Schema(
                {
                    vol.Required("off", default=default_off): int,
                    vol.Required("on", default=default_on): int,
                }
            ),
            description_placeholders={
                "current": var.str_value if var else "?",
                "raw": str(var.raw) if var else "?",
            },
        )

    # --- Number (two steps: pick variable, then min/max/step) ---
    async def async_step_add_number(self, user_input=None):
        if user_input is not None:
            self._pending = {"uri": user_input["uri"], "name": user_input.get("name", "")}
            return await self.async_step_add_number_values()
        return self.async_show_form(
            step_id="add_number",
            data_schema=vol.Schema(
                {vol.Required("uri"): self._uri_selector(), vol.Optional("name", default=""): str}
            ),
        )

    async def async_step_add_number_values(self, user_input=None):
        if user_input is not None:
            self.controls.append(
                {
                    "type": "number",
                    "uri": self._pending["uri"],
                    "name": self._pending["name"],
                    "min": float(user_input["min_value"]),
                    "max": float(user_input["max_value"]),
                    "step": float(user_input["step"]),
                }
            )
            return await self.async_step_init()

        var = await self._read_var(self._pending["uri"])
        sf = (var.scale_factor or 1) if var else 1
        default_step = round(1 / sf, 4)
        current = round(var.raw / sf, var.dec_places) if var else "?"
        return self.async_show_form(
            step_id="add_number_values",
            data_schema=vol.Schema(
                {
                    vol.Required("min_value", default=0): vol.Coerce(float),
                    vol.Required("max_value", default=100): vol.Coerce(float),
                    vol.Required("step", default=default_step): vol.Coerce(float),
                }
            ),
            description_placeholders={
                "current": str(current),
                "unit": (var.unit if var else "") or "-",
                "scale": str(sf),
            },
        )

    # --- Select (single step: pick variable + label=raw lines) ---
    async def async_step_add_select(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            options = _parse_options(user_input.get("options", ""))
            if not options:
                errors["options"] = "invalid_options"
            else:
                self.controls.append(
                    {
                        "type": "select",
                        "uri": user_input["uri"],
                        "name": user_input.get("name", ""),
                        "options": options,
                    }
                )
                return await self.async_step_init()
        return self.async_show_form(
            step_id="add_select",
            data_schema=vol.Schema(
                {
                    vol.Required("uri"): self._uri_selector(),
                    vol.Optional("name", default=""): str,
                    vol.Required("options"): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_remove(self, user_input=None):
        if not self.controls:
            return await self.async_step_init()
        if user_input is not None:
            keep = set(user_input.get("remove", []))
            self._controls = [c for c in self.controls if _control_key(c) not in keep]
            return await self.async_step_init()
        options = [
            selector.SelectOptionDict(value=_control_key(c), label=_control_label(c))
            for c in self.controls
        ]
        return self.async_show_form(
            step_id="remove",
            data_schema=vol.Schema(
                {
                    vol.Optional("remove", default=[]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, multiple=True)
                    )
                }
            ),
        )

    async def async_step_save(self, user_input=None):
        return self.async_create_entry(data={CONF_CONTROLS: self.controls})


def _parse_options(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        label, _, raw = line.rpartition("=")
        label = label.strip()
        try:
            result[label] = int(raw.strip())
        except ValueError:
            continue
    return result


def _control_key(control: dict) -> str:
    return f"{control['type']}:{control['uri']}"


def _control_label(control: dict) -> str:
    name = control.get("name") or control["uri"]
    return f"[{control['type']}] {name}"
