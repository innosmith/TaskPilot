"""Tests für den Skill-Editor (Pfad-Auflösung + Backup-Sicherheitsnetz).

Kein DB/Git nötig: ``get_hermes_home`` wird auf ein temporäres Verzeichnis
gezeigt. Geprüft wird, dass nur existierende Skills aufgelöst werden, Pfad-
Traversal abgewehrt wird und vor dem Überschreiben eine ``.bak``-Kopie entsteht.
"""

import app.services.hermes_config as hc
from app.routers.intelligence import _backup_skill, _resolve_skill_md_path


def _make_skill(home, dir_name: str, frontmatter_name: str, body: str = "Inhalt") -> None:
    skill_dir = home / "skills" / dir_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {frontmatter_name}\ndescription: Test\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_resolve_by_directory_name(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "get_hermes_home", lambda: tmp_path)
    _make_skill(tmp_path, "email-triage", "email-triage")
    path = _resolve_skill_md_path("email-triage")
    assert path is not None and path.name == "SKILL.md"


def test_resolve_by_frontmatter_name(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "get_hermes_home", lambda: tmp_path)
    _make_skill(tmp_path, "dir-abc", "Schöner-Name")
    path = _resolve_skill_md_path("Schöner-Name")
    assert path is not None
    assert path.parent.name == "dir-abc"


def test_unknown_skill_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "get_hermes_home", lambda: tmp_path)
    (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
    assert _resolve_skill_md_path("gibt-es-nicht") is None


def test_path_traversal_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "get_hermes_home", lambda: tmp_path)
    _make_skill(tmp_path, "email-triage", "email-triage")
    assert _resolve_skill_md_path("../../etc/passwd") is None
    assert _resolve_skill_md_path("a/b") is None


def test_backup_creates_bak_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "get_hermes_home", lambda: tmp_path)
    _make_skill(tmp_path, "email-triage", "email-triage", body="Original")
    path = _resolve_skill_md_path("email-triage")
    backup_name = _backup_skill(path)
    backup_path = path.with_name(backup_name)
    assert backup_path.exists()
    assert "Original" in backup_path.read_text(encoding="utf-8")
