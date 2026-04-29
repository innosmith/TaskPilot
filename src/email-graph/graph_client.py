"""Microsoft Graph API Client für E-Mail- und Kalender-Zugriff (OAuth2 Client Credentials Flow).

Scopes: Mail.Read, Mail.ReadWrite, Mail.Send, Calendars.Read, Calendars.ReadWrite (Application-Level).
Konfig via Umgebungsvariablen: GRAPH_TENANT_ID, GRAPH_CLIENT_ID,
GRAPH_CLIENT_SECRET, GRAPH_USER_EMAIL.
"""

import logging
import os
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("taskpilot.graph")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


@dataclass
class GraphConfig:
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    user_email: str = ""

    @classmethod
    def from_env(cls) -> "GraphConfig":
        return cls(
            tenant_id=os.environ.get("GRAPH_TENANT_ID", ""),
            client_id=os.environ.get("GRAPH_CLIENT_ID", ""),
            client_secret=os.environ.get("GRAPH_CLIENT_SECRET", ""),
            user_email=os.environ.get("GRAPH_USER_EMAIL", ""),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.tenant_id and self.client_id and self.client_secret and self.user_email)


@dataclass
class _TokenCache:
    access_token: str = ""
    expires_at: float = 0.0

    @property
    def is_valid(self) -> bool:
        return bool(self.access_token) and time.time() < self.expires_at - 60


class GraphClient:
    """Async MS Graph API Client mit automatischem Token-Refresh."""

    def __init__(self, config: GraphConfig | None = None):
        self.config = config or GraphConfig.from_env()
        self._token = _TokenCache()
        self._http: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def _get_token(self) -> str:
        if self._token.is_valid:
            return self._token.access_token

        client = await self._ensure_client()
        url = TOKEN_URL_TPL.format(tenant=self.config.tenant_id)
        resp = await client.post(
            url,
            data={
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token.access_token = data["access_token"]
        self._token.expires_at = time.time() + data.get("expires_in", 3600)
        logger.info("Graph API Token erneuert (gültig für %ds)", data.get("expires_in", 3600))
        return self._token.access_token

    async def _headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        client = await self._ensure_client()
        headers = await self._headers()
        resp = await client.get(f"{GRAPH_BASE}{path}", headers=headers, params=params)
        if resp.status_code == 403:
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                pass
            raise PermissionError(
                f"Graph API 403 Forbidden -- die App-Registration braucht passende "
                f"Application Permissions mit Admin Consent. "
                f"Prüfe: Mail.Read, Mail.ReadWrite, Mail.Send, Calendars.Read, Calendars.ReadWrite. "
                f"Detail: {detail}"
            )
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, json_body: dict | None = None) -> dict:
        client = await self._ensure_client()
        headers = await self._headers()
        resp = await client.post(f"{GRAPH_BASE}{path}", headers=headers, json=json_body)
        if resp.status_code == 403:
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                pass
            raise PermissionError(
                f"Graph API 403 Forbidden -- fehlende Application Permissions. Detail: {detail}"
            )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def _patch(self, path: str, json_body: dict) -> dict:
        client = await self._ensure_client()
        headers = await self._headers()
        resp = await client.patch(f"{GRAPH_BASE}{path}", headers=headers, json=json_body)
        if resp.status_code == 403:
            raise PermissionError(
                "Graph API 403 Forbidden -- fehlende Application Permissions mit Admin Consent."
            )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def _delete(self, path: str) -> None:
        client = await self._ensure_client()
        headers = await self._headers()
        resp = await client.delete(f"{GRAPH_BASE}{path}", headers=headers)
        if resp.status_code == 403:
            raise PermissionError("Graph API 403 Forbidden -- fehlende Permissions.")
        resp.raise_for_status()

    @property
    def _user_path(self) -> str:
        return f"/users/{self.config.user_email}"

    # ── E-Mail CRUD ──────────────────────────────────────────────

    async def list_folders(self) -> list[dict]:
        """Alle Mail-Ordner des konfigurierten Users."""
        data = await self._get(f"{self._user_path}/mailFolders", {"$top": "100"})
        return data.get("value", [])

    async def list_emails(
        self,
        folder: str = "inbox",
        top: int = 20,
        skip: int = 0,
        filter_str: str | None = None,
    ) -> dict:
        """E-Mails aus einem Ordner lesen. Gibt {value, @odata.nextLink} zurück."""
        params: dict[str, str] = {
            "$top": str(top),
            "$skip": str(skip),
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,toRecipients,receivedDateTime,isRead,"
                       "bodyPreview,categories,inferenceClassification,hasAttachments,"
                       "importance,conversationId,flag",
        }
        if filter_str:
            params["$filter"] = filter_str
        return await self._get(f"{self._user_path}/mailFolders/{folder}/messages", params)

    async def get_email(self, message_id: str) -> dict:
        """Einzelne E-Mail mit Body laden."""
        return await self._get(
            f"{self._user_path}/messages/{message_id}",
            {"$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,"
                        "body,bodyPreview,categories,inferenceClassification,"
                        "hasAttachments,importance,isRead,conversationId"},
        )

    async def get_email_categories(self, message_id: str) -> dict:
        """Kategorien und Klassifizierung einer E-Mail."""
        data = await self._get(
            f"{self._user_path}/messages/{message_id}",
            {"$select": "id,categories,inferenceClassification"},
        )
        return {
            "id": data.get("id"),
            "categories": data.get("categories", []),
            "inferenceClassification": data.get("inferenceClassification"),
        }

    async def create_draft(
        self,
        subject: str,
        body_html: str,
        to_recipients: list[str],
        cc_recipients: list[str] | None = None,
        reply_to_id: str | None = None,
    ) -> dict:
        """Entwurf im Drafts-Ordner erstellen."""
        message: dict = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [
                {"emailAddress": {"address": addr}} for addr in to_recipients
            ],
        }
        if cc_recipients:
            message["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc_recipients
            ]

        if reply_to_id:
            return await self._post(
                f"{self._user_path}/messages/{reply_to_id}/createReply",
                {"message": message},
            )
        return await self._post(f"{self._user_path}/messages", message)

    async def send_draft(self, message_id: str) -> None:
        """Existierenden Entwurf versenden."""
        client = await self._ensure_client()
        headers = await self._headers()
        resp = await client.post(
            f"{GRAPH_BASE}{self._user_path}/messages/{message_id}/send",
            headers=headers,
        )
        resp.raise_for_status()

    async def update_draft(
        self,
        message_id: str,
        subject: str | None = None,
        body_html: str | None = None,
        to_recipients: list[str] | None = None,
        cc_recipients: list[str] | None = None,
    ) -> dict:
        """Bestehenden Entwurf aktualisieren (Betreff, Body, Empfaenger)."""
        patch_body: dict = {}
        if subject is not None:
            patch_body["subject"] = subject
        if body_html is not None:
            patch_body["body"] = {"contentType": "HTML", "content": body_html}
        if to_recipients is not None:
            patch_body["toRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in to_recipients
            ]
        if cc_recipients is not None:
            patch_body["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc_recipients
            ]
        if not patch_body:
            return {}
        return await self._patch(
            f"{self._user_path}/messages/{message_id}",
            patch_body,
        )

    async def delete_message(self, message_id: str) -> None:
        """E-Mail oder Entwurf loeschen."""
        client = await self._ensure_client()
        headers = await self._headers()
        resp = await client.delete(
            f"{GRAPH_BASE}{self._user_path}/messages/{message_id}",
            headers=headers,
        )
        resp.raise_for_status()

    async def mark_as_read(self, message_id: str) -> None:
        """E-Mail als gelesen markieren."""
        client = await self._ensure_client()
        headers = await self._headers()
        resp = await client.patch(
            f"{GRAPH_BASE}{self._user_path}/messages/{message_id}",
            headers=headers,
            json={"isRead": True},
        )
        resp.raise_for_status()

    async def set_categories(self, message_id: str, categories: list[str]) -> dict:
        """Outlook-Kategorien auf einer E-Mail setzen (ersetzt bestehende)."""
        return await self._patch(
            f"{self._user_path}/messages/{message_id}",
            {"categories": categories},
        )

    async def get_or_create_folder(
        self, display_name: str, parent_folder: str = "inbox"
    ) -> dict:
        """Mail-Subfolder suchen. Gibt {id, displayName} zurueck.

        Erstellt KEINE neuen Ordner. Wirft ValueError wenn nicht gefunden.
        """
        parent_path = (
            f"{self._user_path}/mailFolders/{parent_folder}/childFolders"
        )
        data = await self._get(
            parent_path,
            {"$filter": f"displayName eq '{display_name}'", "$top": "1"},
        )
        folders = data.get("value", [])
        if folders:
            return {"id": folders[0]["id"], "displayName": folders[0]["displayName"]}

        raise ValueError(
            f"Ordner '{display_name}' existiert nicht unter {parent_folder}. "
            "Neue Ordner duerfen nicht automatisch erstellt werden."
        )

    async def move_to_folder(self, message_id: str, folder_name: str) -> dict:
        """E-Mail in einen bestehenden Subfolder verschieben."""
        folder = await self.get_or_create_folder(folder_name)
        return await self._post(
            f"{self._user_path}/messages/{message_id}/move",
            {"destinationId": folder["id"]},
        )

    async def get_conversation_messages(
        self, conversation_id: str, top: int = 10
    ) -> list[dict]:
        """Alle Nachrichten einer Konversation (Thread) chronologisch."""
        try:
            data = await self._get(
                f"{self._user_path}/messages",
                {
                    "$filter": f"conversationId eq '{conversation_id}'",
                    "$top": str(top),
                    "$select": "id,subject,from,toRecipients,receivedDateTime,"
                               "bodyPreview,body,conversationId",
                },
            )
            msgs = data.get("value", [])
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                logger.warning(
                    "get_conversation_messages $filter fehlgeschlagen (400), Fallback auf $search"
                )
                data = await self._get(
                    f"{self._user_path}/messages",
                    {
                        "$search": f'"conversationId:{conversation_id}"',
                        "$top": str(top),
                        "$select": "id,subject,from,toRecipients,receivedDateTime,"
                                   "bodyPreview,body,conversationId",
                    },
                )
                msgs = data.get("value", [])
            else:
                raise
        msgs.sort(key=lambda m: m.get("receivedDateTime", ""))
        return msgs

    async def search_sender_emails(
        self, sender_email: str, top: int = 5
    ) -> list[dict]:
        """Letzte E-Mails eines bestimmten Absenders (neueste zuerst)."""
        try:
            data = await self._get(
                f"{self._user_path}/messages",
                {
                    "$filter": f"from/emailAddress/address eq '{sender_email}'",
                    "$top": str(top),
                    "$select": "id,subject,from,receivedDateTime,bodyPreview,body,conversationId",
                },
            )
            msgs = data.get("value", [])
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                logger.warning(
                    "search_sender_emails $filter fehlgeschlagen (400), Fallback auf $search"
                )
                data = await self._get(
                    f"{self._user_path}/messages",
                    {
                        "$search": f'"from:{sender_email}"',
                        "$top": str(top),
                        "$select": "id,subject,from,receivedDateTime,bodyPreview,body,conversationId",
                    },
                )
                msgs = data.get("value", [])
            else:
                raise
        msgs.sort(key=lambda m: m.get("receivedDateTime", ""), reverse=True)
        return msgs

    async def search_emails(self, query: str, top: int = 5) -> list[dict]:
        """Volltextsuche ueber alle E-Mails (Graph $search)."""
        data = await self._get(
            f"{self._user_path}/messages",
            {
                "$search": f'"{query}"',
                "$top": str(top),
                "$select": "id,subject,from,receivedDateTime,bodyPreview,conversationId",
            },
        )
        return data.get("value", [])

    async def list_flagged_emails(self, top: int = 20, since_days: int = 180) -> list[dict]:
        """Markierte E-Mails (Outlook-Fahne gesetzt) laden, nur aus den letzten since_days Tagen."""
        import datetime as _dt
        since = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            data = await self._get(
                f"{self._user_path}/messages",
                {
                    "$filter": f"flag/flagStatus eq 'flagged' and receivedDateTime ge {since}",
                    "$top": str(top),
                    "$select": "id,subject,from,receivedDateTime,bodyPreview,"
                               "flag,categories,importance,hasAttachments,conversationId",
                },
            )
        except Exception:
            data = await self._get(
                f"{self._user_path}/messages",
                {
                    "$filter": "flag/flagStatus eq 'flagged'",
                    "$top": "100",
                    "$select": "id,subject,from,receivedDateTime,bodyPreview,"
                               "flag,categories,importance,hasAttachments,conversationId",
                },
            )
        msgs = data.get("value", [])
        msgs.sort(key=lambda m: m.get("receivedDateTime", ""), reverse=True)
        return msgs[:top]

    # ── Kalender CRUD ────────────────────────────────────────────

    async def list_events(
        self,
        start: str,
        end: str,
        top: int = 50,
    ) -> list[dict]:
        """Termine in einem Zeitraum (ISO 8601 datetime strings)."""
        data = await self._get(
            f"{self._user_path}/calendarView",
            {
                "startDateTime": start,
                "endDateTime": end,
                "$top": str(top),
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,location,isAllDay,isCancelled,"
                           "organizer,attendees,bodyPreview,showAs,importance,"
                           "categories,sensitivity,isOrganizer",
            },
        )
        return data.get("value", [])

    async def get_event(self, event_id: str) -> dict:
        """Einzelnen Kalender-Eintrag laden."""
        return await self._get(
            f"{self._user_path}/events/{event_id}",
            {
                "$select": "id,subject,start,end,location,body,isAllDay,"
                           "organizer,attendees,showAs,importance,recurrence",
            },
        )

    async def create_event(
        self,
        subject: str,
        start: str,
        end: str,
        body: str | None = None,
        is_all_day: bool = False,
        location: str | None = None,
        show_as: str = "busy",
    ) -> dict:
        """Neuen Termin / Zeitblocker erstellen."""
        tz = "Europe/Zurich"
        event: dict = {
            "subject": subject,
            "start": {"dateTime": start, "timeZone": tz},
            "end": {"dateTime": end, "timeZone": tz},
            "isAllDay": is_all_day,
            "showAs": show_as,
        }
        if body:
            event["body"] = {"contentType": "HTML", "content": body}
        if location:
            event["location"] = {"displayName": location}
        return await self._post(f"{self._user_path}/events", event)

    async def update_event(self, event_id: str, **fields) -> dict:
        """Termin-Felder aktualisieren."""
        tz = "Europe/Zurich"
        patch: dict = {}
        if "subject" in fields:
            patch["subject"] = fields["subject"]
        if "start" in fields:
            patch["start"] = {"dateTime": fields["start"], "timeZone": tz}
        if "end" in fields:
            patch["end"] = {"dateTime": fields["end"], "timeZone": tz}
        if "show_as" in fields:
            patch["showAs"] = fields["show_as"]
        if "body" in fields:
            patch["body"] = {"contentType": "HTML", "content": fields["body"]}
        return await self._patch(f"{self._user_path}/events/{event_id}", patch)

    async def delete_event(self, event_id: str) -> None:
        """Termin löschen."""
        await self._delete(f"{self._user_path}/events/{event_id}")

    async def find_free_slots(
        self,
        start: str,
        end: str,
        duration_minutes: int = 60,
    ) -> list[dict]:
        """Freie Zeitfenster berechnen (vereinfacht: Lücken zwischen Terminen)."""
        from datetime import datetime as dt, timedelta
        events = await self.list_events(start, end, top=100)
        busy = []
        for ev in events:
            if ev.get("isCancelled") or ev.get("showAs") == "free":
                continue
            s = ev.get("start", {}).get("dateTime", "")
            e = ev.get("end", {}).get("dateTime", "")
            if s and e:
                busy.append((dt.fromisoformat(s.replace("Z", "+00:00")),
                             dt.fromisoformat(e.replace("Z", "+00:00"))))
        busy.sort()

        range_start = dt.fromisoformat(start.replace("Z", "+00:00"))
        range_end = dt.fromisoformat(end.replace("Z", "+00:00"))
        duration = timedelta(minutes=duration_minutes)

        free = []
        cursor = range_start
        for bs, be in busy:
            if cursor + duration <= bs:
                free.append({
                    "start": cursor.isoformat(),
                    "end": bs.isoformat(),
                    "duration_minutes": int((bs - cursor).total_seconds() / 60),
                })
            cursor = max(cursor, be)
        if cursor + duration <= range_end:
            free.append({
                "start": cursor.isoformat(),
                "end": range_end.isoformat(),
                "duration_minutes": int((range_end - cursor).total_seconds() / 60),
            })
        return free

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
