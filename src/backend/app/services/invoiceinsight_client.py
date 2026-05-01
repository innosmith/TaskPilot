"""InvoiceInsight MCP-Client -- verbindet sich per Streamable HTTP zum MCP-Server."""

import json
import logging
from typing import Any

from cachetools import TTLCache
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger("taskpilot.invoiceinsight")

_resource_cache: TTLCache = TTLCache(maxsize=32, ttl=300)
_tool_cache: TTLCache = TTLCache(maxsize=64, ttl=120)


def _parse_content(result: Any) -> Any:
    """Extrahiert JSON aus MCP-Antworten (Resource oder Tool)."""
    if hasattr(result, "contents"):
        parts = []
        for c in result.contents:
            text = getattr(c, "text", None)
            if text:
                try:
                    parts.append(json.loads(text))
                except (json.JSONDecodeError, TypeError):
                    parts.append(text)
        return parts[0] if len(parts) == 1 else parts

    if hasattr(result, "content"):
        for c in result.content:
            text = getattr(c, "text", None)
            if text:
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return text
    return result


class InvoiceInsightClient:
    """Async Client fuer den InvoiceInsight MCP-Server."""

    def __init__(self, url: str, api_key: str):
        self._url = url
        self._api_key = api_key

    async def read_resource(self, uri: str, *, use_cache: bool = True) -> Any:
        if use_cache:
            cached = _resource_cache.get(uri)
            if cached is not None:
                return cached

        async with streamablehttp_client(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}"},
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                raw = await session.read_resource(uri)
                data = _parse_content(raw)
                if use_cache:
                    _resource_cache[uri] = data
                return data

    async def call_tool(self, name: str, arguments: dict | None = None, *, use_cache: bool = False) -> Any:
        cache_key = f"{name}:{json.dumps(arguments or {}, sort_keys=True)}"
        if use_cache:
            cached = _tool_cache.get(cache_key)
            if cached is not None:
                return cached

        async with streamablehttp_client(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}"},
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                raw = await session.call_tool(name, arguments or {})
                data = _parse_content(raw)
                if use_cache:
                    _tool_cache[cache_key] = data
                return data

    async def get_kpis(self) -> dict:
        return await self.read_resource("invoices://kpis")

    async def get_renewal_calendar(self) -> Any:
        return await self.read_resource("invoices://renewal-calendar")

    async def get_cashflow_forecast(self) -> Any:
        return await self.read_resource("invoices://cashflow-forecast")

    async def get_cost_distribution(self) -> Any:
        return await self.read_resource("invoices://cost-distribution")

    async def get_vendor_overview(self) -> Any:
        return await self.read_resource("invoices://vendor-overview")

    async def get_recurring_vs_onetime(self) -> Any:
        return await self.read_resource("invoices://recurring-vs-onetime")

    async def get_data_quality(self) -> Any:
        return await self.read_resource("invoices://data-quality")

    async def get_yoy_comparison(self) -> Any:
        return await self.read_resource("invoices://yoy-comparison")

    async def get_anomalies(self) -> Any:
        return await self.read_resource("invoices://anomalies")

    async def get_metadata(self) -> Any:
        return await self.read_resource("invoices://metadata")

    def invalidate_cache(self) -> None:
        _resource_cache.clear()
        _tool_cache.clear()
