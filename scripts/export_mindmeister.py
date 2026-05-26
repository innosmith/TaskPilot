#!/usr/bin/env python3
"""
MindMeister Export + TaskPilot-Import (Zwei-Phasen-Ansatz)

Phase 1 — Export:  MindMeister API → .mm (FreeMind) + .mind (nativ) Dateien
Phase 2 — Import:  .mm-Datei(en) → TaskPilot Mind-Maps (nur Knoten + Kanten)

Verwendung:
    # 1) Alle Maps exportieren (Backup):
    python scripts/export_mindmeister.py export

    # 2) Einzelne .mm-Datei in TaskPilot importieren:
    python scripts/export_mindmeister.py import --file dataimport/MindMeister/backup/Meine_Map.mm

    # 3) Alle .mm aus einem Ordner importieren:
    python scripts/export_mindmeister.py import --dir dataimport/MindMeister/backup/

    # Import-Ziel waehlen:
    python scripts/export_mindmeister.py import --file ... --target prod

Credentials werden interaktiv abgefragt (inkl. MFA-Code bei Import).
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mm-export")

MM_BASE = "https://www.mindmeister.com"
MM_THROTTLE_S = 0.8
MM_MAX_RETRIES = 4
MM_RETRY_BASE_S = 5.0

EXPORT_DIR = Path("dataimport/MindMeister/backup")
EXPORT_FORMATS = ["mm", "mind"]

TARGET_URLS = {
    "dev": "http://localhost:8000",
    "int": "http://localhost:8100",
    "prod": "http://localhost:8200",
}

def _sanitize_filename(name: str) -> str:
    """Dateiname-sichere Version eines Titels."""
    clean = re.sub(r'[<>:"/\\|?*]', "_", name)
    clean = re.sub(r"\s+", "_", clean).strip("_.")
    return clean[:120] or "unnamed"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: MindMeister API Client + Export
# ═══════════════════════════════════════════════════════════════════════════


class MindMeisterClient:
    def __init__(self, token: str) -> None:
        self._http = httpx.Client(
            base_url=MM_BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
            follow_redirects=True,
        )

    def _request_with_retry(self, url: str, **kwargs: object) -> httpx.Response:
        for attempt in range(MM_MAX_RETRIES + 1):
            time.sleep(MM_THROTTLE_S)
            resp = self._http.get(url, **kwargs)
            if resp.status_code != 429:
                resp.raise_for_status()
                return resp
            retry_after = float(resp.headers.get("Retry-After", MM_RETRY_BASE_S))
            wait = max(retry_after, MM_RETRY_BASE_S) * (2**attempt)
            log.warning(
                "  Rate-Limit (429) — warte %.0fs (Versuch %d/%d)",
                wait,
                attempt + 1,
                MM_MAX_RETRIES,
            )
            time.sleep(wait)
        resp.raise_for_status()
        return resp

    def list_maps(self) -> list[dict]:
        """Alle Maps auflisten via v1 Bridge (mm.maps.getList mit OAuth2-Token)."""
        all_maps: list[dict] = []
        page = 1
        per_page = 100

        while True:
            resp = self._request_with_retry(
                "/services/rest/oauth2",
                params={
                    "method": "mm.maps.getList",
                    "page": page,
                    "per_page": per_page,
                },
            )
            content_type = resp.headers.get("content-type", "")
            log.debug("Response content-type: %s", content_type)
            log.debug("Response body (first 500 chars): %s", resp.text[:500])

            if "xml" in content_type or resp.text.strip().startswith("<"):
                maps = self._parse_map_list_xml(resp.text)
            else:
                data = resp.json()
                maps = self._extract_maps_from_json(data)

            if not maps:
                break

            all_maps.extend(maps)
            if len(maps) < per_page:
                break
            page += 1

        return all_maps

    @staticmethod
    def _extract_maps_from_json(data: dict) -> list[dict]:
        """JSON-Response der v1 Bridge parsen (rsp.maps.map oder flache Liste)."""
        if isinstance(data, list):
            return data

        rsp = data.get("rsp", data)
        if rsp.get("stat") == "fail":
            err = rsp.get("err", {})
            log.error("API-Fehler: %s (Code %s)", err.get("msg"), err.get("code"))
            return []

        maps_obj = rsp.get("maps", {})
        map_list = maps_obj.get("map", [])

        if isinstance(map_list, dict):
            map_list = [map_list]

        result = []
        for m in map_list:
            result.append({
                "id": int(m.get("id", 0)),
                "title": m.get("title", "Untitled"),
                "created": m.get("created", ""),
                "modified": m.get("modified", ""),
                "folder_id": m.get("folder_id", ""),
            })
        return result

    @staticmethod
    def _parse_map_list_xml(xml_text: str) -> list[dict]:
        """v1-XML-Response (<rsp><maps><map .../></maps></rsp>) parsen (Fallback)."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            log.error("Konnte XML-Response nicht parsen: %s", xml_text[:200])
            return []

        maps_elem = root.find(".//maps")
        if maps_elem is None:
            maps_elem = root

        result = []
        for m in maps_elem.findall("map"):
            result.append({
                "id": int(m.get("id", 0)),
                "title": m.get("title", "Untitled"),
                "created": m.get("created", ""),
                "modified": m.get("modified", ""),
            })
        return result

    def get_map_metadata(self, map_id: int) -> dict:
        """Map-Metadaten via v2 API abrufen."""
        resp = self._request_with_retry(f"/api/v2/maps/{map_id}")
        return resp.json()

    def export_map(self, map_id: int, fmt: str) -> bytes:
        """Map im angegebenen Format exportieren via v2 API."""
        resp = self._request_with_retry(f"/api/v2/maps/{map_id}.{fmt}")
        return resp.content

    def close(self) -> None:
        self._http.close()


@dataclass
class ExportStats:
    total: int = 0
    exported: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def run_export(client: MindMeisterClient, out_dir: Path) -> ExportStats:
    """Exportiert alle Maps in .mm + .mind Format."""
    stats = ExportStats()
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Lade Map-Liste von MindMeister …")
    maps = client.list_maps()
    stats.total = len(maps)
    log.info("  %d Maps gefunden\n", stats.total)

    if not maps:
        log.warning("Keine Maps gefunden. Prüfe Token und Abo-Status.")
        return stats

    metadata: list[dict] = []

    for idx, m in enumerate(maps):
        map_id = m["id"]
        title = m.get("title") or f"map_{map_id}"
        safe_name = _sanitize_filename(title)
        log.info(
            "━━━ %d/%d  %s (ID %d) ━━━",
            idx + 1,
            stats.total,
            title,
            map_id,
        )

        meta_entry = {
            "id": map_id,
            "title": title,
            "filename": safe_name,
            "created": m.get("created", ""),
            "modified": m.get("modified", ""),
            "formats_exported": [],
        }

        for fmt in EXPORT_FORMATS:
            try:
                data = client.export_map(map_id, fmt)
                file_path = out_dir / f"{safe_name}.{fmt}"

                # Deduplizierung bei gleichem Dateinamen
                counter = 1
                while file_path.exists():
                    file_path = out_dir / f"{safe_name}_{counter}.{fmt}"
                    counter += 1

                file_path.write_bytes(data)
                meta_entry["formats_exported"].append(fmt)
                log.info("  ✓ %s (%d Bytes)", file_path.name, len(data))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 402:
                    log.warning(
                        "  ✗ %s-Export benötigt höheres Abo (402 Payment Required)",
                        fmt,
                    )
                    meta_entry.setdefault("skipped_formats", []).append(fmt)
                else:
                    msg = f"Map '{title}' (ID {map_id}), Format {fmt}: HTTP {exc.response.status_code}"
                    log.error("  ✗ %s", msg)
                    stats.errors.append(msg)
                    stats.failed += 1
            except Exception as exc:
                msg = f"Map '{title}' (ID {map_id}), Format {fmt}: {exc}"
                log.error("  ✗ %s", msg)
                stats.errors.append(msg)

        if meta_entry["formats_exported"]:
            stats.exported += 1
        metadata.append(meta_entry)

    meta_path = out_dir / "metadata.json"
    meta_path.write_text(
        json.dumps(
            {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "source": "mindmeister",
                "total_maps": stats.total,
                "maps": metadata,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    log.info("\nMetadaten gespeichert: %s", meta_path)

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: FreeMind .mm Parser + TaskPilot Import
# ═══════════════════════════════════════════════════════════════════════════

# Parser liegt in src/backend/app/services/freemind_parser.py — hier nur Wrapper
try:
    from app.services.freemind_parser import parse_freemind_xml
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "backend"))
    from app.services.freemind_parser import parse_freemind_xml


def parse_freemind(mm_path: Path) -> dict:
    """FreeMind .mm Datei in TaskPilot flow_data konvertieren."""
    return parse_freemind_xml(mm_path.read_bytes())


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

    def create_mindmap(self, title: str, flow_data: dict) -> dict:
        self._ensure_auth()
        resp = self._http.post(
            "/api/mindmaps",
            json={
                "title": title,
                "flow_data": flow_data,
                "visibility": "private",
            },
        )
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._http.close()


@dataclass
class ImportStats:
    total: int = 0
    imported: int = 0
    errors: list[str] = field(default_factory=list)


def run_import(
    tp: TaskPilotClient,
    mm_files: list[Path],
) -> ImportStats:
    """Importiert .mm-Dateien als TaskPilot Mind-Maps."""
    stats = ImportStats(total=len(mm_files))

    for idx, mm_file in enumerate(mm_files):
        title = mm_file.stem.replace("_", " ")
        log.info("━━━ %d/%d  %s ━━━", idx + 1, stats.total, title)

        try:
            flow_data = parse_freemind(mm_file)
            n_nodes = len(flow_data["nodes"])
            n_edges = len(flow_data["edges"])
            log.info("  Geparst: %d Knoten, %d Kanten", n_nodes, n_edges)

            result = tp.create_mindmap(title, flow_data)
            log.info("  ✓ Erstellt: %s", result.get("id", "?"))
            stats.imported += 1
        except Exception as exc:
            msg = f"'{mm_file.name}': {exc}"
            log.error("  ✗ %s", msg)
            stats.errors.append(msg)

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def _print_export_report(stats: ExportStats) -> None:
    print(f"\n{'═' * 60}")
    print("  EXPORT REPORT")
    print(f"{'═' * 60}")
    print(f"  Maps gefunden:      {stats.total}")
    print(f"  Erfolgreich:        {stats.exported}")
    print(f"  Fehlgeschlagen:     {stats.failed}")
    if stats.errors:
        print(f"\n  FEHLER ({len(stats.errors)}):")
        for e in stats.errors:
            print(f"    - {e}")
    print(f"{'═' * 60}\n")


def _print_import_report(stats: ImportStats) -> None:
    print(f"\n{'═' * 60}")
    print("  IMPORT REPORT")
    print(f"{'═' * 60}")
    print(f"  Dateien:            {stats.total}")
    print(f"  Importiert:         {stats.imported}")
    if stats.errors:
        print(f"\n  FEHLER ({len(stats.errors)}):")
        for e in stats.errors:
            print(f"    - {e}")
    print(f"{'═' * 60}\n")


def main() -> None:
    import os

    parser = argparse.ArgumentParser(
        description="MindMeister Export + TaskPilot-Import"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- export ---
    p_export = sub.add_parser("export", help="Alle MindMeister-Maps als Backup exportieren")
    p_export.add_argument(
        "--token",
        default=None,
        help="MindMeister Personal Access Token (oder Env TP_MEISTERLABS_TOKEN)",
    )
    p_export.add_argument(
        "--outdir",
        default=str(EXPORT_DIR),
        help=f"Zielverzeichnis (default: {EXPORT_DIR})",
    )

    # --- import ---
    p_import = sub.add_parser("import", help=".mm-Datei(en) in TaskPilot importieren")
    p_import.add_argument("--file", default=None, help="Einzelne .mm-Datei importieren")
    p_import.add_argument("--dir", default=None, help="Alle .mm-Dateien aus Verzeichnis importieren")
    p_import.add_argument(
        "--target",
        choices=["dev", "int", "prod"],
        default="int",
        help="Ziel-Umgebung (default: int)",
    )
    p_import.add_argument("--tp-email", default=None, help="TaskPilot Owner-E-Mail")
    p_import.add_argument("--tp-password", default=None, help="TaskPilot Owner-Passwort")

    args = parser.parse_args()

    # ── EXPORT ──────────────────────────────────────────────────────────
    if args.command == "export":
        token = args.token or os.environ.get("TP_MEISTERLABS_TOKEN")
        if not token:
            token = getpass.getpass("MindMeister Personal Access Token: ")
        if not token:
            log.error("Token fehlt.")
            sys.exit(1)

        client = MindMeisterClient(token)
        try:
            out_dir = Path(args.outdir)
            stats = run_export(client, out_dir)
            _print_export_report(stats)
            if stats.failed > 0:
                sys.exit(2)
        finally:
            client.close()

    # ── IMPORT ──────────────────────────────────────────────────────────
    elif args.command == "import":
        mm_files: list[Path] = []

        if args.file:
            p = Path(args.file)
            if not p.exists() or not p.suffix == ".mm":
                log.error("Datei nicht gefunden oder kein .mm-Format: %s", p)
                sys.exit(1)
            mm_files = [p]
        elif args.dir:
            d = Path(args.dir)
            if not d.is_dir():
                log.error("Verzeichnis nicht gefunden: %s", d)
                sys.exit(1)
            mm_files = sorted(d.glob("*.mm"))
        else:
            default_dir = EXPORT_DIR
            if default_dir.is_dir():
                mm_files = sorted(default_dir.glob("*.mm"))
            if not mm_files:
                log.error(
                    "Keine .mm-Dateien gefunden. Verwende --file oder --dir."
                )
                sys.exit(1)

        log.info("%d .mm-Datei(en) zum Import gefunden", len(mm_files))
        for f in mm_files:
            log.info("  - %s", f.name)
        print()

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
            stats = run_import(tp, mm_files)
            _print_import_report(stats)
            if stats.errors:
                sys.exit(2)
        finally:
            tp.close()


if __name__ == "__main__":
    main()
