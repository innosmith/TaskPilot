"""Bexio Buchhaltungs-API Client (async, httpx-basiert).

Authentifizierung via Bearer Token (persönlicher API-Token).
API v2.0 für Kontakte, Aufträge, Projekte.
API v3.0 für /users/me.
"""

import asyncio
import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger("taskpilot.bexio")

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

BASE_URL_V2 = "https://api.bexio.com/2.0"
BASE_URL_V3 = "https://api.bexio.com/3.0"


@dataclass
class BexioConfig:
    api_token: str = ""

    @classmethod
    def from_env(cls) -> "BexioConfig":
        return cls(api_token=os.environ.get("TP_BEXIO_API_TOKEN", ""))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token)


class BexioClient:
    """Async Bexio API Client mit Rate-Limit-Retry."""

    def __init__(self, config: BexioConfig | None = None):
        self.config = config or BexioConfig.from_env()
        self._http: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.config.api_token}",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._http

    async def _request(
        self, method: str, url: str, params: dict | None = None, json_body: dict | list | None = None
    ) -> dict | list:
        client = await self._ensure_client()
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.request(method, url, params=params, json=json_body)
                if resp.status_code == 429:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning("Bexio Rate-Limit (429), Retry in %.1fs", delay)
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                if resp.status_code == 204:
                    return {}
                return resp.json()
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES - 1:
                    raise
                logger.warning("Bexio HTTP-Fehler: %s, Retry %d", exc, attempt + 1)
                await asyncio.sleep(RETRY_BASE_DELAY)
        return {}

    async def _get_v2(self, path: str, params: dict | None = None) -> dict | list:
        return await self._request("GET", f"{BASE_URL_V2}{path}", params=params)

    async def _post_v2(self, path: str, body: dict | list) -> dict | list:
        return await self._request("POST", f"{BASE_URL_V2}{path}", json_body=body)

    async def _get_v3(self, path: str, params: dict | None = None) -> dict | list:
        return await self._request("GET", f"{BASE_URL_V3}{path}", params=params)

    # ── Verbindungstest ──────────────────────────────────────

    async def test_connection(self) -> dict:
        """Verbindung testen via /3.0/users/me (nicht in v2 vorhanden)."""
        try:
            data = await self._get_v3("/users/me")
            if isinstance(data, dict):
                return {
                    "ok": bool(data.get("id")),
                    "name": f"{data.get('firstname', '')} {data.get('lastname', '')}".strip(),
                    "email": data.get("email", ""),
                }
        except Exception:
            pass
        return {"ok": False}

    # ── Kontakte ─────────────────────────────────────────────

    async def list_contacts(self, limit: int = 50, offset: int = 0) -> list[dict]:
        params = {"limit": str(limit), "offset": str(offset)}
        data = await self._get_v2("/contact", params)
        return data if isinstance(data, list) else []

    async def get_contact(self, contact_id: int) -> dict:
        data = await self._get_v2(f"/contact/{contact_id}")
        return data if isinstance(data, dict) else {}

    async def create_contact(self, payload: dict) -> dict:
        data = await self._post_v2("/contact", payload)
        return data if isinstance(data, dict) else {}

    async def search_contact_by_name(self, name: str) -> list[dict]:
        """Kontakte per POST /contact/search nach Name suchen."""
        search_body = [
            {"field": "name_1", "value": name, "criteria": "like"}
        ]
        data = await self._post_v2("/contact/search", search_body)
        return data if isinstance(data, list) else []

    async def search_contact_by_email(self, email: str) -> list[dict]:
        """Kontakte per POST /contact/search nach E-Mail suchen."""
        search_body = [
            {"field": "mail", "value": email, "criteria": "like"}
        ]
        data = await self._post_v2("/contact/search", search_body)
        return data if isinstance(data, list) else []

    # ── Aufträge (kb_order) ──────────────────────────────────

    async def list_orders(self, contact_id: int | None = None, limit: int = 50) -> list[dict]:
        params = {"limit": str(limit)}
        if contact_id:
            params["contact_id"] = str(contact_id)
        data = await self._get_v2("/kb_order", params)
        return data if isinstance(data, list) else []

    async def get_order(self, order_id: int) -> dict:
        data = await self._get_v2(f"/kb_order/{order_id}")
        return data if isinstance(data, dict) else {}

    # ── Rechnungen (kb_invoice) ──────────────────────────────

    async def list_invoices(self, contact_id: int | None = None, limit: int = 50) -> list[dict]:
        params = {"limit": str(limit)}
        if contact_id:
            params["contact_id"] = str(contact_id)
        data = await self._get_v2("/kb_invoice", params)
        return data if isinstance(data, list) else []

    async def get_invoice(self, invoice_id: int) -> dict:
        data = await self._get_v2(f"/kb_invoice/{invoice_id}")
        return data if isinstance(data, dict) else {}

    # ── Projekte ─────────────────────────────────────────────

    async def list_projects(self, limit: int = 50) -> list[dict]:
        params = {"limit": str(limit)}
        data = await self._get_v2("/pr_project", params)
        return data if isinstance(data, list) else []

    async def get_project(self, project_id: int) -> dict:
        data = await self._get_v2(f"/pr_project/{project_id}")
        return data if isinstance(data, dict) else {}
