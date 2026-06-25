from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EtaApiError, EtaError, EtaHackClient, MenuItem, VarInfo, VarValue

_LOGGER = logging.getLogger(__name__)


class EtaHackCoordinator(DataUpdateCoordinator[dict]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: EtaHackClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ETA Hack",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.menu_items: list[MenuItem] = []
        self.var_info_cache: dict[str, VarInfo] = {}
        self._tracked_uris: set[str] = set()

    def track_uri(self, uri: str) -> None:
        self._tracked_uris.add(uri)

    def untrack_uri(self, uri: str) -> None:
        self._tracked_uris.discard(uri)

    async def async_initialize(self) -> None:
        """Fetch menu tree and varinfo cache. Safe to call multiple times."""
        if self.menu_items:
            return
        try:
            self.menu_items = await self.client.get_menu()
        except EtaApiError as exc:
            raise UpdateFailed(f"Failed to fetch menu: {exc}") from exc

        async def _fetch_info(item: MenuItem) -> None:
            try:
                info = await self.client.get_varinfo(item.uri)
                self.var_info_cache[item.uri] = info
            except EtaApiError:
                _LOGGER.debug("Could not fetch varinfo for %s, skipping", item.uri)

        await asyncio.gather(*[_fetch_info(item) for item in self.menu_items])

    async def _async_setup(self) -> None:
        await self.async_initialize()

    async def _async_update_data(self) -> dict:
        vars_data: dict[str, VarValue] = {}
        errors: list[EtaError] = []

        async def _fetch_var(uri: str) -> None:
            try:
                vars_data[uri] = await self.client.get_var(uri)
            except EtaApiError as exc:
                _LOGGER.warning("Failed to fetch variable %s: %s", uri, exc)

        tasks = [_fetch_var(uri) for uri in self._tracked_uris]
        tasks.append(self._fetch_errors(errors))
        await asyncio.gather(*tasks)

        return {"vars": vars_data, "errors": errors}

    async def _fetch_errors(self, out: list[EtaError]) -> None:
        try:
            out.extend(await self.client.get_errors())
        except EtaApiError as exc:
            _LOGGER.warning("Failed to fetch errors: %s", exc)
