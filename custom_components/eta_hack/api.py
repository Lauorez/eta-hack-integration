from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import aiohttp

_NS = "http://www.eta.co.at/rest/v1"


@dataclass
class MenuItem:
    uri: str
    name: str
    path: str  # human-readable breadcrumb, e.g. "Kessel > Counters > Full load hours"


@dataclass
class VarValue:
    uri: str
    str_value: str
    unit: str
    dec_places: int
    scale_factor: int
    adv_text_offset: int
    raw: int


@dataclass
class VarInfo:
    uri: str
    name: str
    full_name: str
    unit: str
    dec_places: int
    scale_factor: int
    adv_text_offset: int
    is_writable: bool
    type_: str
    valid_values: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class EtaError:
    msg: str
    priority: str
    time: str
    description: str


class EtaApiError(Exception):
    pass


class EtaHackClient:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self._session = session
        self._base = f"http://{host}:{port}"

    async def _get_xml(self, path: str) -> ET.Element:
        url = f"{self._base}{path}"
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                resp.raise_for_status()
                text = await resp.text(encoding="utf-8")
        except aiohttp.ClientError as exc:
            raise EtaApiError(f"HTTP error fetching {path}: {exc}") from exc
        try:
            return ET.fromstring(text)
        except ET.ParseError as exc:
            raise EtaApiError(f"XML parse error for {path}: {exc}") from exc

    async def _post_form(self, path: str, data: dict[str, Any]) -> ET.Element:
        url = f"{self._base}{path}"
        try:
            async with self._session.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                text = await resp.text(encoding="utf-8")
        except aiohttp.ClientError as exc:
            raise EtaApiError(f"HTTP error posting to {path}: {exc}") from exc
        try:
            return ET.fromstring(text)
        except ET.ParseError as exc:
            raise EtaApiError(f"XML parse error for {path}: {exc}") from exc

    async def get_api_version(self) -> str:
        root = await self._get_xml("/user/api")
        api_el = root.find(f"{{{_NS}}}api")
        if api_el is None:
            raise EtaApiError("Missing <api> element in /user/api response")
        return api_el.get("version", "unknown")

    async def get_menu(self) -> list[MenuItem]:
        root = await self._get_xml("/user/menu")
        menu_el = root.find(f"{{{_NS}}}menu")
        if menu_el is None:
            raise EtaApiError("Missing <menu> element in /user/menu response")
        items: list[MenuItem] = []
        self._parse_menu_node(menu_el, "", items)
        return items

    def _parse_menu_node(self, node: ET.Element, parent_path: str, items: list[MenuItem]) -> None:
        for child in node:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            name = child.get("name", "")
            uri = child.get("uri", "").lstrip("/")
            path = f"{parent_path} > {name}".lstrip(" > ") if parent_path else name
            if tag == "fub":
                self._parse_menu_node(child, path, items)
            elif tag == "object":
                has_children = len(list(child)) > 0
                if not has_children:
                    items.append(MenuItem(uri=uri, name=name, path=path))
                else:
                    self._parse_menu_node(child, path, items)

    async def get_var(self, uri: str) -> VarValue:
        root = await self._get_xml(f"/user/var/{uri}")
        val_el = root.find(f"{{{_NS}}}value")
        if val_el is None:
            raise EtaApiError(f"Missing <value> element for /user/var/{uri}")
        return VarValue(
            uri=uri,
            str_value=val_el.get("strValue", ""),
            unit=val_el.get("unit", ""),
            dec_places=int(val_el.get("decPlaces", "0")),
            scale_factor=int(val_el.get("scaleFactor", "1")),
            adv_text_offset=int(val_el.get("advTextOffset", "0")),
            raw=int(val_el.text or "0"),
        )

    async def get_varinfo(self, uri: str) -> VarInfo:
        root = await self._get_xml(f"/user/varinfo/{uri}")
        var_info_el = root.find(f"{{{_NS}}}varInfo")
        if var_info_el is None:
            raise EtaApiError(f"Missing <varInfo> element for /user/varinfo/{uri}")
        var_el = var_info_el.find(f"{{{_NS}}}variable")
        if var_el is None:
            raise EtaApiError(f"Missing <variable> element for /user/varinfo/{uri}")

        valid_values: list[tuple[str, int]] = []
        valid_vals_el = var_el.find(f"{{{_NS}}}validValues")
        if valid_vals_el is not None:
            for v in valid_vals_el.findall(f"{{{_NS}}}value"):
                sv = v.get("strValue", "")
                raw = int(v.text or "0")
                valid_values.append((sv, raw))

        type_el = var_el.find(f"{{{_NS}}}type")
        type_ = type_el.text if type_el is not None else ""

        return VarInfo(
            uri=uri,
            name=var_el.get("name", ""),
            full_name=var_el.get("fullName", var_el.get("name", "")),
            unit=var_el.get("unit", ""),
            dec_places=int(var_el.get("decPlaces", "0")),
            scale_factor=int(var_el.get("scaleFactor", "1")),
            adv_text_offset=int(var_el.get("advTextOffset", "0")),
            is_writable=var_el.get("isWritable", "0") == "1",
            type_=type_ or "",
            valid_values=valid_values,
        )

    async def set_var(
        self,
        uri: str,
        value: int,
        begin: int | None = None,
        end: int | None = None,
    ) -> None:
        data: dict[str, Any] = {"value": str(value)}
        if begin is not None:
            data["begin"] = str(begin)
        if end is not None:
            data["end"] = str(end)
        root = await self._post_form(f"/user/var/{uri}", data)
        if root.find(f"{{{_NS}}}success") is None:
            raise EtaApiError(f"No <success> in response for POST /user/var/{uri}")

    async def get_errors(self) -> list[EtaError]:
        root = await self._get_xml("/user/errors")
        errors_el = root.find(f"{{{_NS}}}errors")
        if errors_el is None:
            return []
        result: list[EtaError] = []
        for fub in errors_el.findall(f"{{{_NS}}}fub"):
            for err in fub.findall(f"{{{_NS}}}error"):
                result.append(
                    EtaError(
                        msg=err.get("msg", ""),
                        priority=err.get("priority", ""),
                        time=err.get("time", ""),
                        description=(err.text or "").strip(),
                    )
                )
        return result
