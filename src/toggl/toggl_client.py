"""Toggl Track API Client (async, httpx-basiert).

Authentifizierung via HTTP Basic Auth ({api_token}:api_token).
API v9 für Workspaces, Clients, Projects.
Reports API v3 für Zeiteinträge.
"""

import asyncio
import base64
import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger("taskpilot.toggl")

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

BASE_URL = "https://api.track.toggl.com/api/v9"
REPORTS_URL = "https://api.track.toggl.com/reports/api/v3"


@dataclass
class TogglConfig:
    api_token: str = ""
    workspace_id: int = 0

    @classmethod
    def from_env(cls) -> "TogglConfig":
        ws = os.environ.get("TP_TOGGL_WORKSPACE_ID", "0")
        return cls(
            api_token=os.environ.get("TP_TOGGL_API_TOKEN", ""),
            workspace_id=int(ws) if ws.isdigit() else 0,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token)

    @property
    def auth_header(self) -> str:
        """HTTP Basic Auth: base64({api_token}:api_token)."""
        creds = f"{self.api_token}:api_token"
        return "Basic " + base64.b64encode(creds.encode()).decode()


class TogglClient:
    """Async Toggl Track API Client mit Rate-Limit-Retry."""

    def __init__(self, config: TogglConfig | None = None):
        self.config = config or TogglConfig.from_env()
        self._http: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                headers={"Authorization": self.config.auth_header},
                timeout=30.0,
            )
        return self._http

    async def _request(
        self, method: str, url: str, params: dict | None = None, json_body: dict | None = None
    ) -> dict | list:
        client = await self._ensure_client()
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.request(method, url, params=params, json=json_body)
                if resp.status_code == 429:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning("Toggl Rate-Limit (429), Retry in %.1fs", delay)
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
                logger.warning("Toggl HTTP-Fehler: %s, Retry %d", exc, attempt + 1)
                await asyncio.sleep(RETRY_BASE_DELAY)
        return {}

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        return await self._request("GET", f"{BASE_URL}{path}", params=params)

    async def _post(self, path: str, body: dict) -> dict | list:
        return await self._request("POST", f"{BASE_URL}{path}", json_body=body)

    async def _put(self, path: str, body: dict) -> dict | list:
        return await self._request("PUT", f"{BASE_URL}{path}", json_body=body)

    async def _post_reports(self, path: str, body: dict) -> dict | list:
        return await self._request("POST", f"{REPORTS_URL}{path}", json_body=body)

    # ── Verbindungstest ──────────────────────────────────────

    async def test_connection(self) -> dict:
        """Verbindung testen via /me."""
        data = await self._get("/me")
        if isinstance(data, dict):
            return {
                "ok": bool(data.get("id")),
                "name": data.get("fullname", ""),
                "email": data.get("email", ""),
                "default_workspace_id": data.get("default_workspace_id"),
            }
        return {"ok": False}

    async def me(self) -> dict:
        data = await self._get("/me")
        return data if isinstance(data, dict) else {}

    # ── Workspaces ───────────────────────────────────────────

    async def list_workspaces(self) -> list[dict]:
        data = await self._get("/me/workspaces")
        return data if isinstance(data, list) else []

    # ── Clients ──────────────────────────────────────────────

    async def list_clients(self, workspace_id: int | None = None) -> list[dict]:
        ws = workspace_id or self.config.workspace_id
        if not ws:
            return []
        data = await self._get(f"/workspaces/{ws}/clients")
        return data if isinstance(data, list) else []

    async def get_client(self, workspace_id: int, client_id: int) -> dict:
        data = await self._get(f"/workspaces/{workspace_id}/clients/{client_id}")
        return data if isinstance(data, dict) else {}

    async def create_client(self, workspace_id: int | None, name: str) -> dict:
        ws = workspace_id or self.config.workspace_id
        data = await self._post(f"/workspaces/{ws}/clients", {"name": name, "wid": ws})
        return data if isinstance(data, dict) else {}

    async def search_clients(self, name: str, workspace_id: int | None = None) -> list[dict]:
        """Clients lokal nach Name filtern (Toggl hat keine Server-seitige Suche)."""
        all_clients = await self.list_clients(workspace_id)
        term = name.lower()
        return [c for c in all_clients if term in (c.get("name") or "").lower()]

    # ── Projects ─────────────────────────────────────────────

    async def list_projects(
        self,
        workspace_id: int | None = None,
        client_ids: list[int] | None = None,
        active: bool | None = True,
    ) -> list[dict]:
        ws = workspace_id or self.config.workspace_id
        if not ws:
            return []
        params: dict[str, str] = {}
        if active is not None:
            params["active"] = "true" if active else "false"
        if client_ids:
            params["client_ids"] = ",".join(str(i) for i in client_ids)
        data = await self._get(f"/workspaces/{ws}/projects", params or None)
        return data if isinstance(data, list) else []

    async def get_project(self, workspace_id: int, project_id: int) -> dict:
        data = await self._get(f"/workspaces/{workspace_id}/projects/{project_id}")
        return data if isinstance(data, dict) else {}

    async def create_project(
        self,
        workspace_id: int | None,
        name: str,
        client_id: int | None = None,
        billable: bool = True,
    ) -> dict:
        ws = workspace_id or self.config.workspace_id
        body: dict = {"name": name, "wid": ws, "is_private": False, "billable": billable}
        if client_id:
            body["client_id"] = client_id
        data = await self._post(f"/workspaces/{ws}/projects", body)
        return data if isinstance(data, dict) else {}

    async def search_projects(self, name: str, workspace_id: int | None = None) -> list[dict]:
        """Projekte lokal nach Name filtern."""
        all_projects = await self.list_projects(workspace_id, active=None)
        term = name.lower()
        return [p for p in all_projects if term in (p.get("name") or "").lower()]

    # ── Time Entries (Reports API v3) ────────────────────────

    async def search_time_entries(
        self,
        workspace_id: int | None,
        start_date: str,
        end_date: str,
        client_ids: list[int] | None = None,
        project_ids: list[int] | None = None,
    ) -> list[dict]:
        """Zeiteinträge via Reports API v3 suchen (POST /workspace/{id}/search/time_entries)."""
        ws = workspace_id or self.config.workspace_id
        if not ws:
            return []
        body: dict = {"start_date": start_date, "end_date": end_date}
        if client_ids:
            body["client_ids"] = client_ids
        if project_ids:
            body["project_ids"] = project_ids
        data = await self._post_reports(f"/workspace/{ws}/search/time_entries", body)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("time_entries", data.get("data", []))
        return []

    # ── Billable Rates & Summary Reports ─────────────────────

    async def get_project_with_rate(
        self, project_id: int, workspace_id: int | None = None
    ) -> dict:
        """Einzelprojekt inkl. rate (Cents) und currency."""
        ws = workspace_id or self.config.workspace_id
        if not ws:
            return {}
        data = await self._get(f"/workspaces/{ws}/projects/{project_id}")
        return data if isinstance(data, dict) else {}

    async def get_projects_summary(
        self,
        start_date: str,
        end_date: str,
        workspace_id: int | None = None,
    ) -> dict:
        """Projekt-Summary: billable_amount_in_cents, rates[], billable_seconds.

        POST /reports/api/v3/workspace/{ws}/projects/summary
        """
        ws = workspace_id or self.config.workspace_id
        if not ws:
            return {}
        body = {"start_date": start_date, "end_date": end_date}
        data = await self._post_reports(f"/workspace/{ws}/projects/summary", body)
        return data if isinstance(data, dict) else {}

    async def get_summary_by_project(
        self,
        start_date: str,
        end_date: str,
        workspace_id: int | None = None,
        billable: bool | None = True,
    ) -> list[dict]:
        """Summary Report gruppiert nach Projekt mit sum, rate, cur, time.

        POST /reports/api/v3/workspace/{ws}/summary/time_entries
        Response-Gruppen enthalten: title, time, cur, sum, rate
        """
        ws = workspace_id or self.config.workspace_id
        if not ws:
            return []
        body: dict = {
            "start_date": start_date,
            "end_date": end_date,
            "grouping": "projects",
            "sub_grouping": "time_entries",
            "distinguish_rates": True,
        }
        if billable is not None:
            body["billable"] = billable
        data = await self._post_reports(f"/workspace/{ws}/summary/time_entries", body)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("groups", data.get("data", []))
        return []
