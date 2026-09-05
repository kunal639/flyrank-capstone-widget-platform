import ipaddress
import json
import math
from collections.abc import Iterable
from typing import Any, Protocol
from urllib.parse import quote
from urllib.request import urlopen


class GeoProvider(Protocol):
    def lookup(self, ip_address: str) -> dict[str, Any] | None: ...


def _fetch_json(url: str) -> dict[str, Any] | None:
    with urlopen(url, timeout=1) as response:  # noqa: S310 - fixed provider URLs
        return json.loads(response.read(10_000))


class IpApiProvider:
    def lookup(self, ip_address: str) -> dict[str, Any] | None:
        data = _fetch_json(f"https://ipapi.co/{quote(ip_address)}/json/")
        if data.get("error"):
            return None
        return {
            "country": data.get("country_name"),
            "city": data.get("city"),
            "region": data.get("region"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
        }


class IpWhoIsProvider:
    def lookup(self, ip_address: str) -> dict[str, Any] | None:
        data = _fetch_json(f"https://ipwho.is/{quote(ip_address)}")
        if not data.get("success", False):
            return None
        return {
            "country": data.get("country"),
            "city": data.get("city"),
            "region": data.get("region"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
        }


def _text_value(value: Any) -> str | None:
    return value[:100] if isinstance(value, str) else None


def _coordinate_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None
    return coordinate if math.isfinite(coordinate) else None


class GeoEnricher:
    def __init__(self, providers: Iterable[GeoProvider]):
        self.providers = tuple(providers)

    def enrich(self, ip_address: str) -> dict[str, Any]:
        try:
            if not ipaddress.ip_address(ip_address).is_global:
                return {}
        except ValueError:
            return {}

        for provider in self.providers:
            try:
                geo_data = provider.lookup(ip_address)
            except Exception:
                continue
            if geo_data:
                return {
                    "country": _text_value(geo_data.get("country")),
                    "city": _text_value(geo_data.get("city")),
                    "region": _text_value(geo_data.get("region")),
                    "latitude": _coordinate_value(geo_data.get("latitude")),
                    "longitude": _coordinate_value(geo_data.get("longitude")),
                }
        return {}
