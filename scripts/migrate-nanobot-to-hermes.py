#!/usr/bin/env python3
"""Einmalige Migration der Agent-Assets von Nanobot (~/.nanobot) nach Hermes (~/.hermes).

Uebernimmt verlustfrei Skills, Memory, Benutzerprofil, Schreibstil und Identitaet,
damit beim Wechsel auf die Hermes-Runtime nichts verloren geht:

    skills/*.md              -> ~/.hermes/skills/
    MEMORY.md                -> ~/.hermes/memories/MEMORY.md
    USER.md                  -> ~/.hermes/memories/USER.md
    schreibstil-anthony.md   -> ~/.hermes/schreibstil-anthony.md
    SOUL.md                  -> ~/.hermes/SOUL.md
    history.jsonl            -> ~/.hermes/memories/history-nanobot-import.jsonl (Archiv)

Das Skript ist idempotent und nicht-destruktiv: Es liest nur aus dem
Nanobot-Workspace und schreibt nach ~/.hermes. Bestehende Hermes-Dateien werden
nur mit ``--force`` ueberschrieben.

Aufruf:
    python scripts/migrate-nanobot-to-hermes.py [--dry-run] [--force] \\
        [--nanobot ~/.nanobot/workspace] [--hermes ~/.hermes]
"""

import argparse
import os
import shutil
import sys
from pathlib import Path


def _find(candidates: list[Path]) -> Path | None:
    """Erstes existierendes File aus einer Kandidatenliste."""
    for c in candidates:
        if c.is_file():
            return c
    return None


def migrate(nanobot: Path, hermes: Path, *, dry_run: bool, force: bool) -> int:
    if not nanobot.exists():
        print(f"FEHLER: Nanobot-Workspace nicht gefunden: {nanobot}", file=sys.stderr)
        return 1

    skills_dst = hermes / "skills"
    memories_dst = hermes / "memories"

    actions: list[tuple[Path, Path]] = []

    # 1) Skills (Verzeichnis)
    skills_src = nanobot / "skills"
    if skills_src.is_dir():
        for f in sorted(skills_src.glob("*.md")):
            actions.append((f, skills_dst / f.name))
        # Unterverzeichnisse (z.B. email-triage-workflow/) mitnehmen
        for sub in sorted(p for p in skills_src.iterdir() if p.is_dir()):
            for f in sorted(sub.rglob("*")):
                if f.is_file():
                    actions.append((f, skills_dst / sub.name / f.relative_to(sub)))

    # 2) Einzeldateien (mit Fallback-Suchpfaden, da Layout variieren kann)
    single_files = {
        "MEMORY.md": (
            [nanobot / "memory" / "MEMORY.md", nanobot / "MEMORY.md"],
            memories_dst / "MEMORY.md",
        ),
        "USER.md": (
            [nanobot / "USER.md", nanobot / "memory" / "USER.md"],
            memories_dst / "USER.md",
        ),
        "schreibstil-anthony.md": (
            [nanobot / "schreibstil-anthony.md", nanobot / "memory" / "schreibstil-anthony.md"],
            hermes / "schreibstil-anthony.md",
        ),
        "SOUL.md": (
            [nanobot / "SOUL.md", nanobot / "memory" / "SOUL.md"],
            hermes / "SOUL.md",
        ),
    }
    for label, (candidates, dst) in single_files.items():
        src = _find(candidates)
        if src:
            actions.append((src, dst))
        else:
            print(f"  (uebersprungen, nicht gefunden: {label})")

    # 3) history.jsonl als Archiv (anderer Zielname)
    history_src = _find([nanobot / "memory" / "history.jsonl", nanobot / "history.jsonl"])
    if history_src:
        actions.append((history_src, memories_dst / "history-nanobot-import.jsonl"))

    if not actions:
        print("Nichts zu migrieren.")
        return 0

    copied = skipped = 0
    for src, dst in actions:
        if dst.exists() and not force:
            print(f"  SKIP (existiert)  {dst}")
            skipped += 1
            continue
        print(f"  COPY  {src}  ->  {dst}")
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        copied += 1

    print(f"\nFertig: {copied} kopiert, {skipped} uebersprungen"
          + (" (dry-run, nichts geschrieben)" if dry_run else ""))
    if skipped and not force:
        print("Hinweis: bestehende Dateien mit --force ueberschreiben.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migriert Nanobot-Assets nach Hermes.")
    parser.add_argument("--nanobot", default=os.path.expanduser("~/.nanobot/workspace"),
                        help="Nanobot-Workspace (Default: ~/.nanobot/workspace)")
    parser.add_argument("--hermes", default=os.path.expanduser("~/.hermes"),
                        help="Hermes-Home (Default: ~/.hermes)")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nicht kopieren")
    parser.add_argument("--force", action="store_true", help="Bestehende Hermes-Dateien ueberschreiben")
    args = parser.parse_args()

    return migrate(
        Path(args.nanobot).expanduser(),
        Path(args.hermes).expanduser(),
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
