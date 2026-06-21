"""Prompt-Templates und Analyse-Typen für die LLM-Finanzanalyse.

Single Source of Truth für:
  - die verfügbaren Analyse-Typen (Galerie im Frontend),
  - die benötigten Snapshot-Sektionen pro Typ,
  - die geforderten Modell-Capabilities (thinking / deep_research),
  - den Treuhänder-System-Prompt und die typ-spezifischen Instruktionen.
"""

from typing import Any

# ── Treuhänder-/CFO-System-Prompt ───────────────────────
SYSTEM_PROMPT = """# Rolle
Du bist ein Senior Schweizer Treuhänder und CFO-Sparringspartner mit eidgenössischem \
Diplom (Treuhandexperte) und langjähriger Erfahrung in der Beratung inhabergeführter \
KMU. Du analysierst die Finanzen eines inhabergeführten Schweizer Klein-KMU \
(Einzelinhaber, Beratung/KI, GmbH nach OR) auf dem Niveau eines \
Verwaltungsrats-Reportings. Der konkrete Firmenname ist bewusst nicht genannt; \
beziehe dich neutral auf „das Unternehmen".

# Auftrag
Liefere eine präzise, entscheidungsorientierte Analyse, die der Inhaber ohne \
Finanzausbildung sofort versteht und die zugleich fachlich einem Treuhänder standhält.

# Arbeitsprinzipien (nicht verhandelbar)
1. Datentreue: Nutze AUSSCHLIESSLICH die im Kontext gelieferten Zahlen. Erfinde, \
runde oder extrapoliere keine Werte ohne explizite Kennzeichnung. Fehlt eine Grösse, \
benenne die Datenlücke und erkläre, was sie für die Aussagekraft bedeutet.
2. Nachrechnen: Leite Kennzahlen aus den Rohdaten ab und zeige bei nicht-trivialen \
Werten die Rechenbasis. Prüfe Plausibilität (Bilanz-Differenz, Vorzeichen, Ausreisser).
3. Einordnen: Vergleiche jede Kennzahl gegen die Richtwerte unten und bewerte sie mit \
Ampel (grün = gut, gelb = beobachten, rot = kritisch). Kontextualisiere für ein \
Einpersonen-Beratungsunternehmen (die „Personalquote" ist faktisch v. a. der Inhaberlohn).
4. Priorisieren: Empfehlungen nach Wirkung x Dringlichkeit, jeweils mit erwartetem \
Effekt (CHF oder %), Aufwand und Zeithorizont.
5. Annahmen kennzeichnen: Jede Annahme klar als solche markieren.
6. Keine Generik: Keine Lehrbuch-Floskeln. Jede Aussage hängt an einer konkreten Zahl \
aus dem Kontext.

# Fachrahmen
- Recht/Rechnungslegung: Schweizer OR (Art. 957 ff.), Swiss GAAP FER/OR, Kontenrahmen KMU.
- GmbH-Spezifika: Eigenkapital & gesetzliche Reserven, Gewinnverwendung, \
Inhaber-/Geschäftsführerlohn vs. Dividende, verdeckte Gewinnausschüttung, MWST \
(effektiv vs. Saldosteuersatz).

# Richtwerte Schweizer KMU (Orientierung, keine Zielvorgaben des Kunden)
- Eigenkapitalquote: solide > 30 %, komfortabel > 50 %.
- Liquiditätsgrad 1 (Cash Ratio) > 20 %; Grad 2 (Quick Ratio) 100-120 %; \
Grad 3 (Current Ratio) 150-200 %.
- Anlagedeckungsgrad 2 > 100 %.
- EBITDA-Marge Dienstleistung: gesund > 15 %.
- DSO (Debitorenfrist): gut < 30 Tage, akzeptabel < 45 Tage.
- Working Capital positiv; liquide Reichweite (Runway): komfortabel > 6 Monate.

# Output-Kontrakt
- Beginne IMMER mit einem **Management-Summary** (3-6 Bullet-Punkte): Gesamt-Ampel, \
wichtigste Erkenntnisse und Top-3-Massnahmen — so, dass es allein gelesen ausreicht. \
Danach folgen die vertiefenden Sektionen zum Detail-Einstieg.
- Stelle Kennzahlen als Markdown-Tabelle dar: | Kennzahl | Wert | Richtwert | Bewertung |.
- Schliesse mit „Annahmen & Datenlücken" und einer priorisierten Massnahmen-Tabelle: \
| Massnahme | Erwarteter Effekt | Aufwand | Frist |.
- Sprache: Schweizer Hochdeutsch (ss statt scharfes S, korrekte Umlaute ä/ö/ü). \
Sauberes Markdown, kurze Absätze; Fachbegriffe bei Erstnennung knapp erklären.

# Selbstprüfung vor Abgabe
Stimmen alle Zahlen mit dem Kontext überein? Ist jede Kennzahl eingeordnet und \
bewertet? Sind die Empfehlungen konkret, quantifiziert und priorisiert? Sind \
Datenlücken benannt?
"""

# ── Wiederverwendbarer Baustein: Lohn vs. Dividende (GmbH-Inhaber) ──
_SALARY_DIVIDEND_BLOCK = (
    "Lohn vs. Dividende (GmbH-Inhaber): Gib eine konkrete, begründete Empfehlung zur "
    "Aufteilung Geschäftsführerlohn vs. Dividende. Rechne dabei ZWINGEND konsistent:\n"
    "- Gehe vom effektiv ausgewiesenen Personalaufwand (Jahres-Hochrechnung im Snapshot) als "
    "aktuellem Lohn aus — schätze die Lohnhöhe NICHT frei.\n"
    "- Wenn du eine Lohnsenkung empfiehlst, rechne die Wirkung vollständig durch: ein tieferer "
    "Lohn erhöht den steuerbaren Jahresgewinn um denselben Betrag. Die mögliche Dividende muss "
    "sich am daraus resultierenden, hochgerechneten Jahresgewinn (plus ausschüttbare Reserven/"
    "Saldovortrag) orientieren — NICHT an einem Token-Betrag. Zeige die Brücke: Lohn alt → Lohn "
    "neu → zusätzlicher Gewinn → realistisch ausschüttbare Dividende.\n"
    "- Berücksichtige: (a) marktkonformer Mindestlohn (Risiko verdeckte Gewinnausschüttung bei zu "
    "tiefem Lohn; AHV stört sich nie an zu hohem Lohn), (b) Sozialversicherungen (AHV/IV/EO/ALV "
    "~10.6% paritätisch bzw. ~5.3% Arbeitnehmer, BVG) — WICHTIG: AHV/IV/EO-Beiträge sind NICHT "
    "plafoniert (sie fallen auf dem GESAMTEN Lohn an, es gibt keine Beitrags-Obergrenze); "
    "plafoniert ist nur die AHV-Maximalrente, weshalb Lohnbestandteile über dem "
    "rentenbildenden Niveau keine höhere AHV-Rente mehr erzeugen. Lohn baut AHV/BVG-Ansprüche und "
    "steuerlich absetzbare BVG-Einkäufe auf, Dividende nicht. (c) Doppelbelastung der Dividende (Gewinnsteuer "
    "GmbH + Teilbesteuerung der Dividende, Bund 70%, kantonal je nach Kanton 50-70% ab 10% "
    "Beteiligung), (d) Grenzsteuersatz nach Kanton/Zivilstand, (e) Liquidität für die Ausschüttung.\n"
    "- Steuer-Kontext: Nutze den im Snapshot-Kopf angegebenen Kanton und Zivilstand. Sind sie "
    "angegeben, rechne kantonsspezifisch (z. B. Teilbesteuerungssatz, ungefährer Grenzsteuersatz) "
    "und markiere Sätze als Annahme; fehlen sie, weise dies als Datenlücke aus statt einen "
    "Kanton zu erfinden.\n"
    "- Stelle die Empfehlung als Optimierungs-Option dar, nicht als Pflicht: ein höherer Lohn kann "
    "bewusst gewollt sein (Altersvorsorge/BVG, einfache Verhältnisse). Nenne eine Lohn- UND eine "
    "Dividenden-Bandbreite mit nachvollziehbarer Rechnung und den getroffenen Annahmen."
)


# ── Typ-spezifische Instruktionen ────────────────────────
# Jede Instruktion: Ziel · Vorgehen · Pflicht-Kennzahlen · Output-Struktur · Qualität.
_INSTRUCTIONS: dict[str, str] = {
    "financial_health": (
        "## Analyse: Finanzielle Gesundheit\n"
        "Ziel: Ganzheitliches Bild der finanziellen Lage mit klarer Gesamt-Ampel und "
        "Fokus auf die drei grössten Hebel.\n\n"
        "Vorgehen:\n"
        "- Ertragslage aus YoY + Übersicht ableiten (Umsatzwachstum, Marge, EBITDA, Personalquote).\n"
        "- Kapital-/Vermögensstruktur aus der Saldenbilanz (EK-Quote, Liquiditätsgrade, "
        "Working Capital, Anlagedeckung).\n"
        "- Liquidität/Runway aus Banksaldo, Burn Rate und offenen Debitoren.\n\n"
        "Pflicht-Kennzahlen (mit Richtwert-Einordnung): EK-Quote, Liquiditätsgrad 1/2/3, "
        "EBITDA-Marge, Personalquote, DSO, Runway.\n\n"
        "Output-Struktur:\n"
        "1. Management-Summary (Gesamt-Ampel, Kernbefunde, Top-3-Massnahmen)\n"
        "2. Ertragslage (YoY-Tabelle mit Bewertung). Verwende für die Umsatzentwicklung "
        "ZWINGEND die Sektion „Jahresvergleich (YoY)“ (stichtagsgleicher Vergleich nur "
        "abgeschlossener Monate) — leite KEINEN Umsatzrückgang aus der Differenz der "
        "Brutto-YTD-Werte der KPI-Übersicht ab, da diese den laufenden, oft noch nicht "
        "fakturierten Monat enthält. Falls eine Jahresrechnung hochgeladen wurde, deren "
        "Vorjahres-Erfolgsrechnung für den vollständigen Vergleich nutzen.\n"
        "3. Vermögens- & Kapitalstruktur (Kennzahlen-Tabelle; falls eine Jahresrechnung "
        "vorliegt, deren Schlussbilanz als Eröffnungsbilanz verwenden und damit die "
        "geschätzte EK-Quote sowie den rekonstruierten Saldovortrag korrigieren)\n"
        "4. Liquidität & Runway (Reichweite in Monaten inkl. Rechenbasis; Szenario bei Umsatzausfall)\n"
        "5. Inhaber-Vergütung: " + _SALARY_DIVIDEND_BLOCK + "\n"
        "6. Stärken / Schwächen / Risiken\n"
        "7. Annahmen & Datenlücken + Massnahmen-Tabelle\n\n"
        "Qualität: Jede Kennzahl eingeordnet; keine Aussage ohne zugrundeliegende Zahl."
    ),
    "fiduciary_review": (
        "## Analyse: Treuhand-Review (abschlussnah)\n"
        "Ziel: Review wie vor dem Jahresabschluss — Plausibilität, Risiken, "
        "Optimierungen, offene Punkte für den Treuhänder.\n\n"
        "Vorgehen:\n"
        "- Bilanz plausibilisieren (Bilanz-Differenz, Vorzeichen, fehlende Eröffnungssalden, Abgrenzungen).\n"
        "- Erfolgsrechnung nach Konto durchgehen (Aufwandstruktur, Ausreisser, Wiederholungsmuster).\n"
        "- Steuer-/MWST-Plausibilität und GmbH-Themen würdigen.\n\n"
        "Pflicht-Kennzahlen: EK-Quote & Reserven-Lage, Bilanz-Differenz, "
        "Aufwandquoten der grössten Konten, EBITDA/Gewinn-Indikation.\n\n"
        "Output-Struktur:\n"
        "1. Management-Summary (Gesamteinschätzung, kritische Punkte)\n"
        "2. Bilanz-Plausibilisierung (Auffälligkeiten, Differenz, Abgrenzungsbedarf; falls eine "
        "Jahresrechnung vorliegt, deren Schlussbilanz als Eröffnungsbilanz gegen die aus dem "
        "Journal abgeleiteten Bestände abgleichen und den rekonstruierten Saldovortrag durch den "
        "effektiven Wert ersetzen)\n"
        "3. Erfolgsrechnung (Aufwand nach Konto, Ausreisser, Tabelle)\n"
        "4. Steuern & MWST (Saldosteuer-Plausibilität, Gewinnsteuer-Indikation, stille/offene Reserven)\n"
        "5. GmbH-spezifisch & Gewinnverwendung: " + _SALARY_DIVIDEND_BLOCK + " Würdige zusätzlich "
        "Gewinnverwendung und Reservenbildung.\n"
        "6. Offene Punkte & Handlungsempfehlungen für den Abschluss (Tabelle)\n\n"
        "Qualität: Jede Auffälligkeit mit Konto/Betrag belegt; Buchungs-/Belegvorschläge konkret."
    ),
    "liquidity_forecast": (
        "## Analyse: Liquidität & Cashflow (vorausschauend)\n"
        "Ziel: Liquiditätslage heute und zum Jahresende beurteilen, Engpässe früh erkennen, "
        "Massnahmen ableiten.\n\n"
        "Vorgehen:\n"
        "- Ausgangslage aus Banksaldo, Liquiditätsgraden und Working Capital.\n"
        "- Zuflussseite aus Debitoren, Pipeline/Run-Rate und DSO-Effekt modellieren.\n"
        "- Abflussseite aus Kreditoren, wiederkehrenden Kosten und Burn Rate.\n"
        "- Mindestens zwei Szenarien (Base, konservativ) bis Jahresende.\n\n"
        "Pflicht-Kennzahlen: Liquiditätsgrad 1/2/3, Working Capital, Burn Rate, "
        "Runway (Monate), DSO, prognostizierter Jahresend-Saldo.\n\n"
        "Output-Struktur:\n"
        "1. Management-Summary (Ampel Liquidität heute/Jahresende)\n"
        "2. Aktuelle Liquidität (Kennzahlen-Tabelle)\n"
        "3. Zuflussseite (Debitoren, Pipeline, DSO-Effekt)\n"
        "4. Abflussseite (Kreditoren, Fixkosten, anstehende Zahlungen)\n"
        "5. Szenarien (Base/konservativ, Jahresend-Saldo) + Frühwarn-Schwellen\n"
        "6. Annahmen & Datenlücken + Massnahmen zur Liquiditätssicherung (Tabelle)\n\n"
        "Qualität: Szenarien mit nachvollziehbaren Annahmen; Engpassmonat klar benannt."
    ),
    "debtor_analysis": (
        "## Analyse: Debitoren & Kundenrisiko\n"
        "Ziel: Kundenkonzentration, Zahlungsverhalten und Fakturierungs-/Auslastungsrisiko "
        "beurteilen und gegensteuern.\n\n"
        "Vorgehen:\n"
        "- Klumpenrisiko über Umsatzanteile der Top-Kunden (inkl. YoY-Vergleich).\n"
        "- Zahlungsverhalten über DSO, offene Posten und Aging.\n"
        "- Auslastung/Fakturierung über Toggl (billable ratio, Monatsprognose).\n\n"
        "Pflicht-Kennzahlen: DSO, Top-1/Top-3-Umsatzanteil (Konzentration), offene Debitoren, "
        "billable ratio, Monatsprognose.\n\n"
        "Output-Struktur:\n"
        "1. Management-Summary (Ampel Kundenrisiko)\n"
        "2. Kundenkonzentration (Top-Kunden-Tabelle, Anteile am Umsatz YTD, Klumpenrisiko)\n"
        "3. Zahlungsverhalten (DSO, offene Posten je Kunde; ein detailliertes Aging "
        "nach Fälligkeitsbuckets nur, falls Fälligkeitsdaten vorliegen — sonst diese "
        "Datenlücke benennen statt schätzen)\n"
        "4. Auslastung & Fakturierung (billable ratio, Monatsprognose)\n"
        "5. Empfehlungen (Mahnwesen, Diversifikation, Pricing) — Massnahmen-Tabelle\n\n"
        "Qualität: Konzentration quantifiziert (%-Anteile aus Umsatz YTD); Empfehlungen "
        "kundenspezifisch; keine erfundenen Aging-/Fälligkeitswerte."
    ),
    "cost_optimization": (
        "## Analyse: Kosten- & Tool-Optimierung (Deep Research)\n"
        "Ziel: Software-/Tool- und Betriebskosten gegen den Markt prüfen und konkretes, "
        "belegtes Sparpotenzial (CHF/Jahr) ausweisen.\n\n"
        "Vorgehen (Recherche-Protokoll je relevanten Posten):\n"
        "- Identifiziere wiederkehrende Tool-/Software-/Abo-Kosten aus Kreditoren & Einzelkonten.\n"
        "- Recherchiere pro Posten: Zweck, aktueller Marktpreis (mit Quelle + Abrufdatum), "
        "1-2 ernsthafte Alternativen, Bundling-/Jahresabo-Optionen, Wechselaufwand, "
        "geschätzte Ersparnis CHF/Jahr.\n"
        "- Erkenne Redundanzen (überlappende Tools) und ungenutzte/zu grosse Abos.\n\n"
        "Pflicht-Outputs: Vergleichstabelle | Tool | Zweck | Ist-Kosten CHF/Jahr | "
        "Alternative | Markt-Preis (Quelle, Datum) | Ersparnis CHF/Jahr | Wechselaufwand |, "
        "sowie ein Quellenverzeichnis mit Abrufdatum.\n\n"
        "Output-Struktur:\n"
        "1. Management-Summary (Sparpotenzial total CHF/Jahr, Top-3-Hebel)\n"
        "2. Kostenstruktur (wiederkehrend vs. einmalig, grösste Positionen)\n"
        "3. Tool-/Software-Audit (Vergleichstabelle wie oben)\n"
        "4. Redundanzen & Konsolidierung\n"
        "5. Priorisierter Massnahmenplan (Quick Wins vs. strategisch, je CHF/Jahr & Aufwand)\n"
        "6. Quellenverzeichnis (URL + Abrufdatum)\n\n"
        "Qualität: Jede Markt-/Preisaussage mit Quelle + Datum belegt; Ersparnisse summiert; "
        "keine Empfehlung ohne Wechselaufwand-Einschätzung."
    ),
}

# ── Analyse-Typen-Katalog ────────────────────────────────
# capabilities: Modell muss MINDESTENS diese Capabilities besitzen (siehe /api/models).
ANALYSIS_TYPES: list[dict[str, Any]] = [
    {
        "id": "financial_health",
        "title": "Finanzielle Gesundheit",
        "description": "Ganzheitliche Kennzahlen-Analyse: Ertrag, Kapitalstruktur, Liquidität, Runway.",
        "icon": "Activity",
        "sections": ["overview", "balance_sheet", "cashflow_forecast", "yoy", "expenses_by_category"],
        "capabilities": ["thinking"],
        "default_anonymize": True,
        "default_model_hint": "anthropic/claude-opus oder gemini/gemini-3.5-pro",
    },
    {
        "id": "fiduciary_review",
        "title": "Treuhand-Review",
        "description": "Abschlussnahes Review: Bilanz-Plausibilisierung, ER, Steuern/MWST, GmbH-Themen.",
        "icon": "ClipboardCheck",
        "sections": ["overview", "balance_sheet", "cashflow_forecast", "expenses_by_category", "expenses_by_account", "yoy"],
        "capabilities": ["thinking"],
        "default_anonymize": True,
        "default_model_hint": "anthropic/claude-opus",
    },
    {
        "id": "liquidity_forecast",
        "title": "Liquidität & Cashflow",
        "description": "Vorausschauende Liquiditätsanalyse mit Zufluss-/Abflussseite und Szenarien.",
        "icon": "Droplets",
        "sections": ["overview", "balance_sheet", "cashflow_forecast", "debtors", "creditors"],
        "capabilities": ["thinking"],
        "default_anonymize": True,
        "default_model_hint": "gemini/gemini-3.5-pro oder anthropic/claude-opus",
    },
    {
        "id": "debtor_analysis",
        "title": "Debitoren & Kundenrisiko",
        "description": "Kundenkonzentration, Zahlungsverhalten (DSO/Aging), Auslastung und Empfehlungen.",
        "icon": "Users",
        "sections": ["overview", "debtors"],
        "capabilities": ["thinking"],
        "default_anonymize": True,
        "default_model_hint": "anthropic/claude-opus",
    },
    {
        "id": "cost_optimization",
        "title": "Kosten- & Tool-Optimierung (Deep Research)",
        "description": "Flaggschiff: Software-/Tool-Kosten gegen den Markt prüfen, Sparpotenziale mit Web-Recherche.",
        "icon": "Search",
        "sections": ["creditors", "expenses_by_account", "expenses_by_category"],
        "capabilities": ["deep_research"],
        "default_anonymize": True,
        "default_model_hint": "gemini/deep-research oder perplexity/sonar-deep-research",
    },
]

_TYPES_BY_ID = {t["id"]: t for t in ANALYSIS_TYPES}


def get_analysis_type(analysis_type: str) -> dict[str, Any] | None:
    return _TYPES_BY_ID.get(analysis_type)


def build_user_prompt(analysis_type: str, snapshot_markdown: str) -> str:
    """Setzt die typ-spezifische Instruktion mit dem Finanz-Snapshot zusammen."""
    instruction = _INSTRUCTIONS.get(
        analysis_type, "Analysiere die folgenden Finanzdaten und gib eine fundierte Einschätzung."
    )
    return (
        f"{instruction}\n\n"
        "---\n\n"
        "Hier die Finanzdaten als Kontext (alle Beträge in CHF):\n\n"
        f"{snapshot_markdown}\n\n"
        "---\n\n"
        "Hinweis: Falls ein Abschnitt „Hochgeladene Jahresrechnung / Finanzbeleg\" "
        "vorhanden ist, behandle ihn als verlässlichste Primärquelle und gleiche die "
        "aus dem Journal abgeleiteten Kennzahlen (insb. Saldovortrag, Eigenkapital, "
        "Bilanzpositionen) damit ab. Weiche Abweichungen klar aus und benenne sie.\n"
    )
