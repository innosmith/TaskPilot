#!/usr/bin/env python3
"""
MeisterTask → TaskPilot Migration (Zwei-Phasen-Ansatz)

Phase 1 — Export:  MeisterTask API → JSON-Datei (langsam, rate-limit-sicher)
Phase 2 — Import:  JSON-Datei → TaskPilot API (beliebig oft wiederholbar)

Verwendung:
    # 1) Export aus MeisterTask in JSON:
    python scripts/migrate_meistertask.py export

    # 2) Import in TaskPilot (Integration):
    python scripts/migrate_meistertask.py import --target int

    # 2b) Import in TaskPilot (Produktion):
    python scripts/migrate_meistertask.py import --target prod

    # Optional: eigene JSON-Datei angeben:
    python scripts/migrate_meistertask.py import --file meistertask_export_20260513.json

Credentials werden interaktiv abgefragt (inkl. MFA-Code bei Import).
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mt-migrate")

MT_BASE = "https://www.meistertask.com/api"
MT_PAGE_SIZE = 200
MT_THROTTLE_S = 0.5
MT_MAX_RETRIES = 4
MT_RETRY_BASE_S = 5.0
MT_PROJECT_PAUSE_S = 2.0

TARGET_URLS = {
    "dev": "http://localhost:8000",
    "int": "http://localhost:8100",
    "prod": "http://localhost:8200",
}

ARCHIVE_KEYWORDS = {"done", "erledigt", "archiv", "archive", "abgeschlossen", "fertig"}

MT_COLORS = {
    "d93651": "#D93651",
    "ff9f1a": "#FF9F1A",
    "ffd500": "#FFD500",
    "8acc47": "#8ACC47",
    "47cc8a": "#47CC8A",
    "30bfbf": "#30BFBF",
    "00aaff": "#00AAFF",
    "8f7ee6": "#8F7EE6",
    "98aab3": "#98AAB3",
}


def _mt_color(raw: str | None) -> str | None:
    """MeisterTask-Farbe (hex ohne #) → #RRGGBB."""
    if not raw:
        return None
    clean = raw.lstrip("#").lower()
    return MT_COLORS.get(clean, f"#{clean.upper()}")


def _is_archive_section(name: str) -> bool:
    return any(kw in name.lower() for kw in ARCHIVE_KEYWORDS)


@dataclass
class Stats:
    projects: int = 0
    columns: int = 0
    tasks: int = 0
    tags: int = 0
    tag_assignments: int = 0
    checklist_items: int = 0
    comments: int = 0
    errors: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: MeisterTask API Client + Export
# ═══════════════════════════════════════════════════════════════════════════


class MeisterTaskClient:
    def __init__(self, token: str) -> None:
        self._http = httpx.Client(
            base_url=MT_BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

    def _request_with_retry(self, url: str, params: dict) -> httpx.Response:
        for attempt in range(MT_MAX_RETRIES + 1):
            time.sleep(MT_THROTTLE_S)
            resp = self._http.get(url, params=params)
            if resp.status_code != 429:
                resp.raise_for_status()
                return resp
            retry_after = float(resp.headers.get("Retry-After", MT_RETRY_BASE_S))
            wait = max(retry_after, MT_RETRY_BASE_S) * (2 ** attempt)
            log.warning(
                "  Rate-Limit (429) — warte %.0fs (Versuch %d/%d)",
                wait, attempt + 1, MT_MAX_RETRIES,
            )
            time.sleep(wait)
        resp.raise_for_status()
        return resp

    def _get_paginated(self, url: str, params: dict | None = None) -> list[dict]:
        params = dict(params or {})
        params.setdefault("items", MT_PAGE_SIZE)
        page = 1
        results: list[dict] = []
        while True:
            params["page"] = page
            resp = self._request_with_retry(url, params)
            batch = resp.json()
            if not batch:
                break
            results.extend(batch)
            if len(batch) < MT_PAGE_SIZE:
                break
            page += 1
        return results

    def get_projects(self, *, status: str = "active") -> list[dict]:
        return self._get_paginated("/projects", {"status": status})

    def get_sections(self, project_id: int) -> list[dict]:
        return self._get_paginated(f"/projects/{project_id}/sections")

    def get_tasks(self, section_id: int, *, status: str = "open") -> list[dict]:
        return self._get_paginated(f"/sections/{section_id}/tasks", {"status": status})

    def get_labels(self, project_id: int) -> list[dict]:
        return self._get_paginated(f"/projects/{project_id}/labels")

    def get_task_labels(self, task_id: int) -> list[dict]:
        return self._get_paginated(f"/tasks/{task_id}/labels")

    def get_checklist_items(self, task_id: int) -> list[dict]:
        return self._get_paginated(f"/tasks/{task_id}/checklist_items")

    def get_comments(self, task_id: int) -> list[dict]:
        return self._get_paginated(f"/tasks/{task_id}/comments")

    def close(self) -> None:
        self._http.close()


def run_export(mt: MeisterTaskClient) -> dict:
    """Liest alle aktiven Projekte mit Details und gibt ein JSON-serialisierbares Dict zurück."""
    export_data: dict = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "source": "meistertask",
        "projects": [],
    }

    log.info("Lade aktive MeisterTask-Projekte …")
    mt_projects = mt.get_projects(status="active")
    log.info("  %d aktive Projekte gefunden\n", len(mt_projects))

    for p_idx, p in enumerate(mt_projects):
        if p_idx > 0:
            log.info("  … Pause (%.0fs) …", MT_PROJECT_PAUSE_S)
            time.sleep(MT_PROJECT_PAUSE_S)

        log.info("━━━ %d/%d  %s (MT-ID %d) ━━━", p_idx + 1, len(mt_projects), p["name"], p["id"])

        sections_raw = mt.get_sections(p["id"])
        sections = [s for s in sections_raw if s.get("status") == 1]
        sections.sort(key=lambda s: s.get("sequence", 0))
        log.info("  %d aktive Sections", len(sections))

        labels = mt.get_labels(p["id"])
        log.info("  %d Labels", len(labels))

        project_data: dict = {
            "mt_id": p["id"],
            "name": p["name"],
            "notes": p.get("notes") or "",
            "status": p.get("status"),
            "sections": [],
            "labels": labels,
        }

        total_tasks = 0
        for s in sections:
            tasks = mt.get_tasks(s["id"], status="open")
            log.info("  Section «%s»: %d offene Tasks", s["name"], len(tasks))

            enriched_tasks = []
            for t in tasks:
                task_labels = mt.get_task_labels(t["id"])
                checklist = mt.get_checklist_items(t["id"])
                comments = mt.get_comments(t["id"])

                enriched_tasks.append({
                    **t,
                    "_labels": task_labels,
                    "_checklist_items": checklist,
                    "_comments": comments,
                })
                total_tasks += 1

            project_data["sections"].append({
                **s,
                "_tasks": enriched_tasks,
            })

        log.info("  → %d Tasks total exportiert", total_tasks)
        export_data["projects"].append(project_data)

    return export_data


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: TaskPilot API Client + Import
# ═══════════════════════════════════════════════════════════════════════════


class TaskPilotClient:
    def __init__(self, base_url: str, email: str, password: str) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=30)
        self._email = email
        self._password = password
        self._token: str | None = None

    def _ensure_auth(self) -> None:
        if self._token:
            return
        resp = self._http.post(
            "/api/auth/login",
            json={"email": self._email, "password": self._password},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("requires_mfa"):
            mfa_code = input("\nMFA-Code (aus Authenticator-App): ").strip()
            resp2 = self._http.post(
                "/api/auth/login",
                json={
                    "email": self._email,
                    "password": self._password,
                    "mfa_code": mfa_code,
                },
            )
            resp2.raise_for_status()
            data = resp2.json()

        self._token = data["access_token"]
        self._http.headers["Authorization"] = f"Bearer {self._token}"
        log.info("TaskPilot-Login erfolgreich")

    def _post(self, path: str, payload: dict) -> dict:
        self._ensure_auth()
        resp = self._http.post(path, json=payload)
        if resp.status_code == 409:
            log.warning("  Bereits vorhanden: %s", path)
            return resp.json() if resp.text else {}
        resp.raise_for_status()
        return resp.json()

    def create_project(self, payload: dict) -> dict:
        return self._post("/api/projects", payload)

    def create_column(self, project_id: str, payload: dict) -> dict:
        return self._post(f"/api/projects/{project_id}/columns", payload)

    def delete_column(self, project_id: str, col_id: str) -> None:
        self._ensure_auth()
        self._http.delete(f"/api/projects/{project_id}/columns/{col_id}")

    def get_project(self, project_id: str) -> dict:
        self._ensure_auth()
        resp = self._http.get(f"/api/projects/{project_id}")
        resp.raise_for_status()
        return resp.json()

    def create_task(self, payload: dict) -> dict:
        return self._post("/api/tasks", payload)

    def create_tag(self, name: str, color: str) -> dict:
        return self._post("/api/tags", {"name": name, "color": color})

    def assign_tag(self, task_id: str, tag_id: str) -> None:
        self._ensure_auth()
        self._http.post(f"/api/tags/tasks/{task_id}/tags/{tag_id}")

    def add_checklist_item(self, task_id: str, text: str, position: float) -> dict:
        return self._post(
            f"/api/tasks/{task_id}/checklist",
            {"text": text, "position": position},
        )

    def add_comment(self, task_id: str, text: str) -> dict:
        return self._post(f"/api/tasks/{task_id}/activity", {"text": text})

    def close(self) -> None:
        self._http.close()


def run_import(tp: TaskPilotClient, data: dict) -> Stats:
    """Importiert die exportierten Daten in TaskPilot."""
    stats = Stats()

    projects = data.get("projects", [])
    log.info("Importiere %d Projekte aus Export vom %s\n", len(projects), data.get("exported_at", "?"))

    for p in projects:
        log.info("━━━ Projekt: %s ━━━", p["name"])

        sections = p.get("sections", [])
        labels = p.get("labels", [])

        first_color = _mt_color(sections[0].get("color")) if sections else None
        tp_project = tp.create_project({
            "name": p["name"],
            "description": p.get("notes") or "",
            "color": first_color or "#3B82F6",
            "status": "active",
        })
        tp_project_id = tp_project["id"]
        stats.projects += 1
        log.info("  Projekt erstellt: %s", tp_project_id)

        project_detail = tp.get_project(tp_project_id)
        for default_col in project_detail.get("board_columns", []):
            tp.delete_column(tp_project_id, default_col["id"])

        # Sections → Board-Columns
        section_map: dict[int, str] = {}
        for idx, s in enumerate(sections):
            col = tp.create_column(tp_project_id, {
                "name": s["name"],
                "color": _mt_color(s.get("color")),
                "position": float(idx + 1),
                "is_archive": _is_archive_section(s["name"]),
            })
            section_map[s["id"]] = col.get("id", "")
            stats.columns += 1
        log.info("  %d Kolonnen erstellt", len(section_map))

        # Labels → Tags
        label_map: dict[int, str] = {}
        for lbl in labels:
            tag = tp.create_tag(lbl["name"], _mt_color(lbl.get("color")) or "#6B7280")
            if tag and "id" in tag:
                label_map[lbl["id"]] = tag["id"]
                stats.tags += 1

        # Tasks
        for s in sections:
            tp_col_id = section_map.get(s["id"])
            if not tp_col_id:
                continue
            for idx, t in enumerate(s.get("_tasks", [])):
                try:
                    _import_task(tp, t, tp_project_id, tp_col_id, float(idx + 1), label_map, stats)
                except Exception as exc:
                    msg = f"Task '{t.get('name')}' (MT-ID {t.get('id')}): {exc}"
                    log.error("  Fehler: %s", msg)
                    stats.errors.append(msg)

        log.info("")

    return stats


def _import_task(
    tp: TaskPilotClient,
    task: dict,
    tp_project_id: str,
    tp_col_id: str,
    position: float,
    label_map: dict[int, str],
    stats: Stats,
) -> None:
    description = task.get("notes") or ""

    tracked = task.get("tracked_time", 0)
    if tracked and tracked > 0:
        hours, remainder = divmod(tracked, 3600)
        minutes = remainder // 60
        description += f"\n\n---\n_Erfasste Zeit (MeisterTask): {hours}h {minutes}m_"

    due_date = None
    if task.get("due"):
        due_date = task["due"][:10]

    tp_task = tp.create_task({
        "title": task["name"],
        "description": description,
        "project_id": tp_project_id,
        "board_column_id": tp_col_id,
        "board_position": position,
        "due_date": due_date,
        "assignee": "me",
    })
    tp_task_id = tp_task["id"]
    stats.tasks += 1
    log.info("    Task: %s", task["name"][:70])

    # Labels → Tags
    for tl in task.get("_labels", []):
        tp_tag_id = label_map.get(tl.get("label_id"))
        if tp_tag_id:
            tp.assign_tag(tp_task_id, tp_tag_id)
            stats.tag_assignments += 1

    # Checklist-Items
    for ci in task.get("_checklist_items", []):
        tp.add_checklist_item(tp_task_id, ci["name"], float(ci.get("sequence", 0)))
        stats.checklist_items += 1

    # Comments
    for c in sorted(task.get("_comments", []), key=lambda x: x.get("created_at", "")):
        text = c.get("text", "").strip()
        if text:
            tp.add_comment(tp_task_id, text)
            stats.comments += 1


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def _print_report(stats: Stats, phase: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {phase} REPORT")
    print(f"{'═' * 60}")
    print(f"  Projekte:           {stats.projects}")
    print(f"  Board-Kolonnen:     {stats.columns}")
    print(f"  Tasks:              {stats.tasks}")
    print(f"  Tags:               {stats.tags}")
    print(f"  Tag-Zuweisungen:    {stats.tag_assignments}")
    print(f"  Checklist-Items:    {stats.checklist_items}")
    print(f"  Kommentare:         {stats.comments}")
    if stats.errors:
        print(f"\n  FEHLER ({len(stats.errors)}):")
        for e in stats.errors:
            print(f"    - {e}")
    print(f"{'═' * 60}\n")


def _default_export_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"meistertask_export_{ts}.json")


def main() -> None:
    import os

    parser = argparse.ArgumentParser(description="MeisterTask → TaskPilot Migration")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- export ---
    p_export = sub.add_parser("export", help="MeisterTask → JSON-Datei exportieren")
    p_export.add_argument("--mt-token", default=None, help="MeisterTask Personal Access Token")
    p_export.add_argument("--file", default=None, help="Ausgabe-Datei (default: meistertask_export_TIMESTAMP.json)")

    # --- import ---
    p_import = sub.add_parser("import", help="JSON-Datei → TaskPilot importieren")
    p_import.add_argument("--file", default=None, help="JSON-Export-Datei")
    p_import.add_argument("--target", choices=["dev", "int", "prod"], default="int", help="Ziel-Umgebung (default: int)")
    p_import.add_argument("--tp-email", default=None, help="TaskPilot Owner-E-Mail")
    p_import.add_argument("--tp-password", default=None, help="TaskPilot Owner-Passwort")

    args = parser.parse_args()

    # ── EXPORT ──────────────────────────────────────────────────────────
    if args.command == "export":
        mt_token = args.mt_token or os.environ.get("MEISTERTASK_TOKEN")
        if not mt_token:
            mt_token = getpass.getpass("MeisterTask Personal Access Token: ")
        if not mt_token:
            log.error("MeisterTask-Token fehlt.")
            sys.exit(1)

        mt = MeisterTaskClient(mt_token)
        try:
            data = run_export(mt)
        finally:
            mt.close()

        out_path = Path(args.file) if args.file else _default_export_path()
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        n_projects = len(data["projects"])
        n_tasks = sum(
            len(t)
            for p in data["projects"]
            for s in p.get("sections", [])
            for t in [s.get("_tasks", [])]
        )
        log.info("")
        log.info("Export abgeschlossen → %s", out_path)
        log.info("  %d Projekte, %d Tasks", n_projects, n_tasks)
        log.info("")
        log.info("Nächster Schritt:")
        log.info("  python scripts/migrate_meistertask.py import --file %s --target int", out_path)

    # ── IMPORT ──────────────────────────────────────────────────────────
    elif args.command == "import":
        if not args.file:
            exports = sorted(Path(".").glob("meistertask_export_*.json"), reverse=True)
            if not exports:
                log.error("Keine Export-Datei gefunden. Bitte zuerst 'export' ausführen oder --file angeben.")
                sys.exit(1)
            args.file = str(exports[0])
            log.info("Verwende neueste Export-Datei: %s", args.file)

        export_path = Path(args.file)
        if not export_path.exists():
            log.error("Datei nicht gefunden: %s", export_path)
            sys.exit(1)

        data = json.loads(export_path.read_text(encoding="utf-8"))
        log.info("Export geladen: %s (vom %s)", export_path, data.get("exported_at", "?"))

        target_url = TARGET_URLS[args.target]
        log.info("Ziel-Umgebung: %s (%s)", args.target.upper(), target_url)

        tp_email = args.tp_email or os.environ.get("TP_OWNER_EMAIL")
        tp_password = args.tp_password or os.environ.get("TP_OWNER_PASSWORD")
        if not tp_email:
            tp_email = input("TaskPilot Owner-E-Mail: ").strip()
        if not tp_password:
            tp_password = getpass.getpass("TaskPilot Owner-Passwort: ")
        if not tp_email or not tp_password:
            log.error("TaskPilot-Credentials fehlen.")
            sys.exit(1)

        tp = TaskPilotClient(target_url, tp_email, tp_password)
        try:
            tp._ensure_auth()
            stats = run_import(tp, data)
            _print_report(stats, "IMPORT")
            if stats.errors:
                sys.exit(2)
        finally:
            tp.close()


if __name__ == "__main__":
    main()
