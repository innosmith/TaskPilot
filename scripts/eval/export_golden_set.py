#!/usr/bin/env python3
"""Exportiert ein Golden-Set fuer die lokale LLM-Eval aus der TaskPilot-DB.

Zieht reale, vom Berater bestaetigte Triage-Entscheide (``email_triage.status =
'acted'`` mit gesetzter ``triage_class``) als Ground Truth, inklusive der
Eingabe-Felder aus dem Agent-Job und -- falls vorhanden -- der tatsaechlich
versendeten Antwort (aus ``agent_feedback``) als Stil-/Inhalts-Referenz.

Datenschutz: Das Golden-Set enthaelt echte E-Mail-Inhalte und bleibt **lokal**
(``scripts/eval/*.jsonl`` ist gitignored). Der Zugriff erfolgt -- wie im Projekt
ueblich -- via ``docker exec`` auf den Postgres-Container; es werden KEINE
Secrets ausgelesen (User/DB stammen aus der Container-Umgebung).

Beispiel:
    python scripts/eval/export_golden_set.py \
        --container taskpilot-postgres-prod --limit 300 \
        --out scripts/eval/golden_set.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Eine Zeile JSON pro Datensatz waere ideal; wir holen aber ein einziges
# json_agg-Array und schreiben es dann als JSONL, damit das Quoting via psql -At
# robust bleibt (keine Tab-/Newline-Probleme in E-Mail-Bodies).
_QUERY = """
SELECT COALESCE(json_agg(r), '[]'::json) FROM (
  SELECT
    et.message_id,
    et.triage_class                              AS gold_triage_class,
    et.reply_expected                            AS gold_reply_expected,
    et.from_address,
    et.from_name,
    et.subject,
    aj.metadata->>'body_preview'                 AS body_preview,
    aj.metadata->>'conversation_id'              AS conversation_id,
    aj.metadata->>'recipient_type'               AS recipient_type,
    aj.metadata->>'inference_classification'     AS inference_classification,
    (
      SELECT fb.corrected->>'body_html'
      FROM agent_feedback fb
      WHERE fb.agent_job_id = aj.id
        AND fb.feedback_type IN ('draft_edit', 'approved_clean')
        AND COALESCE(fb.corrected->>'body_html', '') <> ''
      ORDER BY fb.created_at DESC
      LIMIT 1
    )                                            AS gold_reply_html
  FROM email_triage et
  JOIN agent_jobs aj ON et.agent_job_id = aj.id
  WHERE et.triage_class IS NOT NULL
    -- 'acted' = bestaetigter Entscheid; 'processing' deckt auto_reply-Faelle ab,
    -- deren versendete Antwort als Draft-Referenz dient (Stuck-Bug, vor Reconcile).
    AND et.status IN ('acted', 'processing')
    AND aj.metadata ? 'email_message_id'
  ORDER BY et.created_at DESC
  LIMIT {limit}
) r;
"""


def _run_psql(container: str, sql: str) -> str:
    """Fuehrt eine Query via ``docker exec`` aus und gibt die rohe Ausgabe zurueck.

    Die Query wird ueber stdin an ``psql -f -`` uebergeben, damit mehrzeilige SQL
    nicht am Shell-/psql-Quoting (Backslash-Meta-Kommandos) scheitert.
    """
    cmd = [
        "docker", "exec", "-i", container, "sh", "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -f -',
    ]
    result = subprocess.run(cmd, input=sql, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(f"psql-Aufruf fehlgeschlagen (Container {container}).")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="taskpilot-postgres-prod",
                        help="Name des Postgres-Containers (Prod: taskpilot-postgres-prod, Dev: taskpilot-postgres)")
    parser.add_argument("--limit", type=int, default=300, help="Maximale Anzahl Datensaetze")
    parser.add_argument("--out", default="scripts/eval/golden_set.jsonl", help="Ausgabedatei (JSONL)")
    args = parser.parse_args()

    raw = _run_psql(args.container, _QUERY.format(limit=int(args.limit)))
    try:
        rows = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        raise SystemExit("Antwort konnte nicht als JSON geparst werden.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with_reply = sum(1 for r in rows if r.get("gold_reply_html"))
    classes: dict[str, int] = {}
    for r in rows:
        classes[r["gold_triage_class"]] = classes.get(r["gold_triage_class"], 0) + 1
    print(f"Golden-Set geschrieben: {out_path} ({len(rows)} Datensaetze)")
    print(f"  Mit versendeter Antwort (Draft-Referenz): {with_reply}")
    print(f"  Klassen-Verteilung: {classes}")


if __name__ == "__main__":
    main()
