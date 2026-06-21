"""FastAPI Router für Finanz-Controlling (Cashflow-Historie + Prognose).

Aggregiert Daten aus Bexio (Buchhaltung) und Toggl Track (Zeiterfassung).
Einnahmen-Historie: Bexio = Master (gestellte Rechnungen).
Einnahmen laufender Monat: Toggl Track (Stunden x Rate).
Ausgaben + Banksaldo: Bexio Journal-API (Buchungen aggregiert).
"""

import logging
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.deps import get_current_user, require_role
from app.database import async_session
from app.models import CapacityAllocation, CapacityProject, User
from app.services.finance_settings import (
    ForecastSettings,
    get_forecast_settings_from_settings,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "bexio"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "toggl"))
from bexio_client import BexioClient, BexioConfig  # noqa: E402
from toggl_client import TogglClient, TogglConfig  # noqa: E402

logger = logging.getLogger("taskpilot.finance")

router = APIRouter(prefix="/api/finance", tags=["finance"])

# ── Cache ────────────────────────────────────────────────
_overview_cache: TTLCache = TTLCache(maxsize=10, ttl=300)
_cashflow_cache: TTLCache = TTLCache(maxsize=10, ttl=900)
_journal_cache: TTLCache = TTLCache(maxsize=5, ttl=600)
_accounts_cache: TTLCache = TTLCache(maxsize=2, ttl=3600)
_toggl_rate_cache: TTLCache = TTLCache(maxsize=4, ttl=3600)

# ── Schweizer KMU-Kontenrahmen Kategorien ────────────────
# Ranges muessen disjunkt sein; _categorize_account iteriert in dict-Order.
# Reihenfolge: spezifischere Ranges vor den Fallback-Ranges.
EXPENSE_CATEGORIES = {
    "loehne": {"label": "Löhne / Gehälter", "range": (5000, 5099)},
    "sozialversicherungen": {"label": "Sozialversicherungen (AHV/IV/EO/ALV)", "range": (5700, 5719)},
    "pensionskasse": {"label": "Pensionskasse (BVG)", "range": (5720, 5729)},
    "uvg_ktg": {"label": "UVG / Krankentaggeld", "range": (5730, 5799)},
    "spesen_personal": {"label": "Spesen / Übriger Personalaufwand", "range": (5800, 5899)},
    "raumkosten": {"label": "Miete / Raumkosten", "range": (6000, 6099)},
    "unterhalt": {"label": "Unterhalt / Reparaturen", "range": (6100, 6199)},
    "fahrzeugkosten": {"label": "Fahrzeugkosten", "range": (6200, 6299)},
    "versicherungen": {"label": "Sachversicherungen", "range": (6300, 6399)},
    "energie": {"label": "Energie / Entsorgung", "range": (6400, 6499)},
    "verwaltung": {"label": "Verwaltungsaufwand / Büro", "range": (6500, 6599)},
    "marketing": {"label": "Werbe- / Reiseaufwand", "range": (6600, 6699)},
    "sonstiger_betrieb": {"label": "Sonstiger Betriebsaufwand", "range": (6700, 6799)},
    "abschreibungen": {"label": "Abschreibungen", "range": (6800, 6899)},
    "finanzaufwand": {"label": "Finanzaufwand", "range": (6900, 6999)},
    "steuern": {"label": "Direkte Steuern", "range": (8900, 8999)},
    "ausserordentlich": {"label": "Ausserordentlicher Aufwand", "range": (8000, 8899)},
}

# Alle Konten-Ranges, die als operativer Aufwand gelten
def _is_expense_account(acc_no: int) -> bool:
    return (4000 <= acc_no <= 6999) or (8000 <= acc_no <= 8999)


# ── Client-Helfer ────────────────────────────────────────

def _get_bexio_client(user: User) -> BexioClient:
    settings = user.settings or {}
    token = settings.get("bexio_api_token") or ""
    if not token:
        from app.config import get_settings
        token = get_settings().bexio_api_token
    if not token:
        raise HTTPException(status_code=400, detail="Bexio API-Token nicht konfiguriert")
    return BexioClient(BexioConfig(api_token=token))


def _get_toggl_client(user: User) -> TogglClient:
    settings = user.settings or {}
    token = settings.get("toggl_api_token") or ""
    ws_id = settings.get("toggl_workspace_id") or 0
    if not token:
        from app.config import get_settings
        app_cfg = get_settings()
        token = app_cfg.toggl_api_token
        ws_id = ws_id or app_cfg.toggl_workspace_id
    if not token:
        raise HTTPException(status_code=400, detail="Toggl API-Token nicht konfiguriert")
    return TogglClient(TogglConfig(api_token=token, workspace_id=int(ws_id or 0)))


# ── Hilfs-Funktionen ─────────────────────────────────────

def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _month_range(months_back: int, months_forward: int) -> list[str]:
    """Erzeuge sortierte Liste von Monats-Keys."""
    today = date.today()
    first_of_month = today.replace(day=1)
    result = []
    for delta in range(-months_back, months_forward + 1):
        m = first_of_month.month + delta
        y = first_of_month.year
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        result.append(f"{y:04d}-{m:02d}")
    return result


def _categorize_account(account_no: int) -> str:
    """Ordne Kontonummer einer KMU-Kategorie zu."""
    for key, cat in EXPENSE_CATEGORIES.items():
        lo, hi = cat["range"]
        if lo <= account_no <= hi:
            return key
    if 4000 <= account_no <= 4999:
        return "materialaufwand"
    if 5100 <= account_no <= 5699:
        return "uebr_personal"
    if 5000 <= account_no <= 5999:
        return "spesen_personal"
    if 6000 <= account_no <= 6999:
        return "sonstiger_betrieb"
    if 8000 <= account_no <= 8999:
        return "ausserordentlich"
    return "sonstige"


def _weighted_forecast(values_3m: list[float], values_12m: list[float]) -> float:
    """Gewichtete Prognose: 60% kurzfristig (3M) / 40% langfristig (12M)."""
    avg_3 = sum(values_3m) / len(values_3m) if values_3m else 0
    avg_12 = sum(values_12m) / len(values_12m) if values_12m else 0
    if not values_3m and not values_12m:
        return 0
    if not values_12m:
        return avg_3
    if not values_3m:
        return avg_12
    return avg_3 * 0.6 + avg_12 * 0.4


def _trailing_12m_avg(values_12m: list[float]) -> float:
    """Geglaetteter Schaetzer fuer klumpige Kategorien (Finanzierung/Investition).

    Jaehrlich anfallende Einmalposten (Dividende, Quartals-MWST, Kontokorrent)
    werden ueber 12 Monate amortisiert: Summe der letzten 12 Monate / 12.
    Anders als der 3M-gewichtete Mix laesst dies ein einzelnes Ereignis in den
    letzten Monaten die Monatsprognose nicht ueberhoehen.
    """
    if not values_12m:
        return 0.0
    return sum(values_12m) / 12.0


def _month_index(month_key: str) -> int:
    """Wandelt "YYYY-MM" in einen fortlaufenden Monatsindex (Jahr*12 + Monat)."""
    y, m = int(month_key[:4]), int(month_key[5:7])
    return y * 12 + (m - 1)


def _seasonal_forecast(
    history_by_month: dict[str, float],
    forecast_months: list[str],
    default_cadence: int,
    threshold: float = 100.0,
) -> dict[str, float]:
    """Saisonale Projektion klumpiger, termingebundener Auszahlungen (MWST, BVG).

    Statt den Betrag ueber alle Monate zu mitteln (was die Spitzen verschmiert),
    werden die naechsten Faelligkeiten auf die Prognosemonate platziert:

    - **Kadenz** (Monatsabstand) wird aus dem JUENGSTEN Muster abgeleitet: zuerst
      aus den Zahlungen des laufenden Jahres. Liegen dort >= 2 Zahlungen vor, wird
      der kleinste Abstand verwendet. Sonst greift ``default_cadence``. So wird
      z. B. der BVG-Wechsel 2026 (jaehrlich -> quartalsweise) korrekt abgebildet
      und nicht der alte Jahres-Rhythmus aus der Historie extrapoliert.
    - **Betrag**: bevorzugt der Schnitt der Zahlungen des laufenden Jahres, sonst
      der Schnitt der letzten bis zu vier beobachteten Zahlungen.
    - In Nicht-Faelligkeitsmonaten ist der Wert 0 -> echte Spitzen bleiben sichtbar.
    """
    result = {m: 0.0 for m in forecast_months}
    events = sorted((m, v) for m, v in history_by_month.items() if v > threshold)
    if not events or not forecast_months:
        return result

    pay_months = [m for m, _ in events]
    today_year = date.today().year
    cy_events = [(m, v) for m, v in events if int(m[:4]) == today_year]

    # Kadenz aus dem laufenden Jahr (juengstes Muster) ableiten.
    cadence = max(1, default_cadence)
    if len(cy_events) >= 2:
        idxs = [_month_index(m) for m, _ in cy_events]
        gaps = [b - a for a, b in zip(idxs, idxs[1:]) if b > a]
        if gaps:
            cadence = min(gaps)

    # Betrag bevorzugt aus dem laufenden Jahr (neue Kadenz hat andere Hoehe).
    if cy_events:
        typ_amount = sum(v for _, v in cy_events) / len(cy_events)
    else:
        recent = [v for _, v in events[-4:]]
        typ_amount = sum(recent) / len(recent)

    last_idx = _month_index(pay_months[-1])
    for m in forecast_months:
        mi = _month_index(m)
        if mi > last_idx and (mi - last_idx) % cadence == 0:
            result[m] = round(typ_amount, 2)
    return result


async def _get_toggl_effective_rates(user: User, since_months: int = 12) -> dict[int, float]:
    """Effektive Stundensaetze (CHF/h) pro Toggl-Projekt aus den letzten Monaten.

    Quelle der Wahrheit fuer zugesagte Arbeit: der tatsaechlich abgerechnete
    Satz = Umsatz / Stunden je Projekt (aus dem billable Summary-Report).
    """
    cached = _toggl_rate_cache.get("eff_rates")
    if cached is not None:
        return cached

    try:
        toggl = _get_toggl_client(user)
    except HTTPException:
        return {}

    today = date.today()
    start = (today.replace(day=1) - timedelta(days=30 * since_months)).isoformat()
    end = today.isoformat()
    try:
        summary = await toggl.get_summary_by_project(start, end, billable=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("Toggl-Effektivsaetze nicht verfuegbar: %s", e)
        return {}

    rates: dict[int, float] = {}
    for group in summary:
        pid = group.get("id")
        if not pid:
            continue
        sub_groups = group.get("sub_groups") or group.get("items") or []
        rev = 0.0
        hrs = 0.0
        for item in sub_groups:
            for rate_info in (item.get("rates") or []):
                secs = rate_info.get("billable_seconds", 0) or 0
                cents = rate_info.get("hourly_rate_in_cents", 0) or 0
                h = secs / 3600
                hrs += h
                rev += h * (cents / 100)
        if hrs > 0 and rev > 0:
            rates[int(pid)] = rev / hrs

    _toggl_rate_cache["eff_rates"] = rates
    return rates


def _resolve_capacity_rate(
    proj: CapacityProject, toggl_rates: dict[int, float], default_rate: float
) -> float:
    """Stundensatz eines Kapazitaetsprojekts aufloesen.

    Hierarchie (erste Quelle gewinnt):
    1. Manueller Satz am Kapazitaetsprojekt (expliziter Override)
    2. Toggl-Effektivsatz ueber die Projekt-Verknuepfung (Quelle der Wahrheit)
    3. Einstellbarer Default-Satz -- nur fuer noch nicht zugesagte Projekte
    """
    if proj.hourly_rate is not None:
        try:
            manual = float(proj.hourly_rate)
            if manual > 0:
                return manual
        except (TypeError, ValueError):
            pass
    if proj.toggl_project_id:
        eff = toggl_rates.get(int(proj.toggl_project_id))
        if eff and eff > 0:
            return eff
    return default_rate


async def _compute_capacity_monthly(
    user: User, month_keys: list[str], fs: ForecastSettings
) -> dict[str, dict]:
    """Pro Monat geplante Kapazitaet (netto) getrennt nach Konfidenz-Schicht.

    - committed: bestaetigte, fakturierbare Projekte
    - pipeline: vorlaeufige (noch nicht zugesagte), fakturierbare Projekte
    Stundensatz je Projekt via Satz-Hierarchie (manuell > Toggl > Default).
    """
    result: dict[str, dict] = defaultdict(
        lambda: {
            "committed_net": 0.0,
            "pipeline_net": 0.0,
            "committed_hours": 0.0,
            "pipeline_hours": 0.0,
        }
    )
    if not month_keys:
        return result
    try:
        async with async_session() as session:
            stmt = (
                select(CapacityAllocation, CapacityProject)
                .join(CapacityProject)
                .where(CapacityAllocation.week_start >= date.fromisoformat(month_keys[0] + "-01"))
                .where(CapacityAllocation.week_start <= date.fromisoformat(month_keys[-1] + "-28"))
                .where(CapacityProject.is_billable == True)  # noqa: E712
                .where(CapacityProject.status.in_(["bestätigt", "vorläufig"]))
            )
            rows = (await session.execute(stmt)).all()
    except Exception as e:  # noqa: BLE001
        logger.warning("Kapazitaetsdaten nicht verfuegbar: %s", e)
        return result

    toggl_rates = await _get_toggl_effective_rates(user)

    for alloc, proj in rows:
        mk = alloc.week_start.strftime("%Y-%m")
        hours = alloc.minutes / 60
        rate = _resolve_capacity_rate(proj, toggl_rates, fs.default_hourly_rate)
        net = hours * rate
        if proj.status == "bestätigt":
            result[mk]["committed_net"] += net
            result[mk]["committed_hours"] += hours
        else:
            result[mk]["pipeline_net"] += net
            result[mk]["pipeline_hours"] += hours
    return result


def _parse_toggl_revenue(summary: list[dict]) -> tuple[float, float]:
    """Berechne Revenue und Stunden aus Toggl v3 Summary Response."""
    total_revenue = 0.0
    total_hours = 0.0
    for group in summary:
        sub_groups = group.get("sub_groups") or group.get("items") or []
        for item in sub_groups:
            rates = item.get("rates") or []
            for rate_info in rates:
                billable_secs = rate_info.get("billable_seconds", 0) or 0
                hourly_cents = rate_info.get("hourly_rate_in_cents", 0) or 0
                hours = billable_secs / 3600
                total_hours += hours
                total_revenue += hours * (hourly_cents / 100)
            if not rates:
                secs = item.get("seconds", 0) or item.get("time", 0) or 0
                total_hours += secs / 3600
    return total_revenue, total_hours


async def _fetch_recent_invoices(bexio: BexioClient, months: int = 13) -> list[dict]:
    """Lade Rechnungen der letzten N Monate via Suchfilter."""
    from_date = (date.today().replace(day=1) - timedelta(days=30 * months)).strftime("%Y-%m-%d")
    try:
        results = await bexio.search_invoices(from_date=from_date)
        if results:
            return results
    except Exception as e:
        logger.warning("Bexio Rechnungssuche fehlgeschlagen: %s -- Fallback auf list", e)
    return await bexio.list_invoices(limit=500)


def _parse_bexio_invoice_total(inv: dict) -> float:
    """Rechnungsbetrag als float (total inkl. MwSt)."""
    for field in ("total", "total_gross"):
        val = inv.get(field)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return 0.0


def _invoice_is_open(inv: dict) -> bool:
    """Rechnung ist offen wenn total_remaining_payments > 0."""
    remaining = inv.get("total_remaining_payments")
    if remaining is not None:
        try:
            return float(remaining) > 0.01
        except (ValueError, TypeError):
            pass
    return inv.get("kb_item_status_id") in (7, 8, 9)


def _revenue_by_month_from_invoices(invoices: list[dict]) -> dict[str, float]:
    """Rechnungen nach Monat gruppieren und Umsatz summieren."""
    revenue: dict[str, float] = defaultdict(float)
    for inv in invoices:
        inv_date = inv.get("is_valid_from") or ""
        if len(inv_date) >= 7:
            mk = inv_date[:7]
            total = _parse_bexio_invoice_total(inv)
            if total > 0:
                revenue[mk] += total
    return dict(revenue)


# ── Journal-Aggregation ──────────────────────────────────

async def _get_accounts_map(bexio: BexioClient) -> dict[int, int]:
    """Kontenplan laden und id -> account_no Mapping erstellen (gecacht)."""
    cached = _accounts_cache.get("map")
    if cached is not None:
        return cached
    accounts = await bexio.list_accounts(limit=500)
    id_to_no = {a.get("id"): int(a.get("account_no", 0) or 0) for a in accounts}
    _accounts_cache["map"] = id_to_no
    logger.info("Kontenplan geladen: %d Konten", len(id_to_no))
    return id_to_no


async def _get_journal_data(
    bexio: BexioClient,
    from_date: str,
    to_date: str,
) -> list[dict]:
    """Journal-Daten laden (gecacht nach Zeitraum)."""
    cache_key = f"{from_date}:{to_date}"
    cached = _journal_cache.get(cache_key)
    if cached is not None:
        return cached
    entries = await bexio.get_journal(from_date, to_date)
    _journal_cache[cache_key] = entries
    return entries


async def _compute_bank_balances_by_account(
    bexio: BexioClient,
    bank_account_ids: set[int],
) -> dict[int, float]:
    """Banksaldo pro Konto: Soll minus Haben seit Geschaeftsjahr-Beginn."""
    fy_start = "2025-01-01"
    try:
        years = await bexio.get_business_years()
        open_years = [y for y in years if y.get("status") == "open"]
        if open_years:
            fy_start = open_years[0].get("start", fy_start)
    except Exception:
        pass

    entries = await _get_journal_data(bexio, fy_start, date.today().isoformat())
    balances: dict[int, float] = {acc_id: 0.0 for acc_id in bank_account_ids}
    for e in entries:
        amount = float(e.get("amount", 0))
        debit = e.get("debit_account_id")
        credit = e.get("credit_account_id")
        if debit in bank_account_ids:
            balances[debit] += amount
        if credit in bank_account_ids:
            balances[credit] -= amount
    return balances


async def _get_fy_start(bexio: BexioClient) -> str:
    """Start des aktuell offenen Geschaeftsjahres (Fallback: laufendes Kalenderjahr)."""
    fy_start = f"{date.today().year}-01-01"
    try:
        years = await bexio.get_business_years()
        open_years = [y for y in years if y.get("status") == "open"]
        if open_years:
            fy_start = open_years[0].get("start", fy_start)
    except Exception:  # noqa: BLE001
        pass
    return fy_start


async def _get_accounts_meta(bexio: BexioClient) -> dict[int, dict]:
    """Kontenplan als id -> {no, name} laden (gecacht)."""
    cached = _accounts_cache.get("meta")
    if cached is not None:
        return cached
    accounts = await bexio.list_accounts(limit=500)
    meta = {
        a.get("id"): {
            "no": int(a.get("account_no", 0) or 0),
            "name": a.get("name") or "",
        }
        for a in accounts
        if a.get("id")
    }
    _accounts_cache["meta"] = meta
    return meta


# ── Bilanz-Klassifikation (Schweizer Kontenrahmen KMU) ───
# Aktiven 1xxx (Soll-Saldo positiv), Passiven 2xxx (Haben-Saldo positiv).
def _classify_bs_account(acc_no: int) -> str | None:
    """Ordnet ein Bilanzkonto einer Bilanz-Gruppe zu (None = kein Bilanzkonto)."""
    if 1000 <= acc_no <= 1099:
        return "fluessige_mittel"
    if 1100 <= acc_no <= 1199:
        return "forderungen"          # Debitoren + uebrige kurzfr. Forderungen (inkl. Vorsteuer)
    if 1200 <= acc_no <= 1299:
        return "vorraete"             # Vorraete + nicht fakturierte Leistungen
    if 1300 <= acc_no <= 1399:
        return "aktive_abgrenzung"
    if 1400 <= acc_no <= 1999:
        return "anlagevermoegen"
    if 2000 <= acc_no <= 2399:
        return "kurzfr_fk"            # kurzfristiges Fremdkapital (Kreditoren, MWST, kurzfr. RA)
    if 2400 <= acc_no <= 2799:
        return "langfr_fk"            # langfristiges Fremdkapital + Rueckstellungen
    if 2800 <= acc_no <= 2999:
        return "eigenkapital"         # Stammkapital + Reserven + Gewinnvortrag
    return None


async def _compute_all_account_balances(bexio: BexioClient) -> dict[int, float]:
    """Roh-Saldo (Soll - Haben) je Konto seit Geschaeftsjahr-Beginn.

    Eroeffnungsbuchungen liegen als regulaere Journal-Eintraege vor, daher ergibt
    die Summe ab Jahresbeginn den aktuellen Konto-Saldo (gleiches Prinzip wie der
    bereits etablierte Banksaldo).
    """
    fy_start = await _get_fy_start(bexio)
    entries = await _get_journal_data(bexio, fy_start, date.today().isoformat())
    balances: dict[int, float] = defaultdict(float)
    for e in entries:
        try:
            amount = float(e.get("amount", 0))
        except (ValueError, TypeError):
            continue
        debit = e.get("debit_account_id")
        credit = e.get("credit_account_id")
        if debit:
            balances[debit] += amount
        if credit:
            balances[credit] -= amount
    return dict(balances)


def _ratio_pct(numerator: float, denominator: float) -> float | None:
    """Verhaeltnis in Prozent, None wenn Nenner ~0."""
    if abs(denominator) < 0.005:
        return None
    return round(numerator / denominator * 100, 1)


async def _compute_balance_sheet(
    bexio: BexioClient,
    accounts_map: dict[int, int],
) -> dict:
    """Saldenbilanz + Bilanzkennzahlen aus dem Journal ableiten.

    Das laufende Jahresergebnis (3xxx - Aufwand) wird dem gebuchten Eigenkapital
    zugeschlagen, damit Aktiven = Passiven gilt und die EK-Quote unterjaehrig
    oekonomisch korrekt ist.
    """
    raw = await _compute_all_account_balances(bexio)
    groups: dict[str, float] = defaultdict(float)
    income_total = 0.0
    expense_total = 0.0

    for acc_id, bal in raw.items():
        acc_no = accounts_map.get(acc_id, 0)
        if not acc_no:
            continue
        cls = _classify_bs_account(acc_no)
        if cls is not None:
            # Aktiven: Soll-Saldo positiv; Passiven: Haben-Saldo positiv (Vorzeichen drehen).
            value = bal if acc_no < 2000 else -bal
            groups[cls] += value
        elif 3000 <= acc_no <= 3999:
            income_total += -bal            # Ertrag = Haben - Soll
        elif _is_expense_account(acc_no):
            expense_total += bal            # Aufwand = Soll - Haben

    fluessige_mittel = round(groups["fluessige_mittel"], 2)
    forderungen = round(groups["forderungen"], 2)
    vorraete = round(groups["vorraete"], 2)
    aktive_abgrenzung = round(groups["aktive_abgrenzung"], 2)
    anlagevermoegen = round(groups["anlagevermoegen"], 2)
    umlaufvermoegen = round(
        fluessige_mittel + forderungen + vorraete + aktive_abgrenzung, 2
    )
    aktiven_total = round(umlaufvermoegen + anlagevermoegen, 2)

    kurzfr_fk = round(groups["kurzfr_fk"], 2)
    langfr_fk = round(groups["langfr_fk"], 2)
    eigenkapital_gebucht = round(groups["eigenkapital"], 2)
    jahresergebnis = round(income_total - expense_total, 2)
    fremdkapital_total = round(kurzfr_fk + langfr_fk, 2)
    # Rekonstruierter Saldovortrag: Ausgleichsgroesse, damit Aktiven = Passiven.
    # Entspricht dem in den Aktiven gebundenen, in Bexio noch nicht ins Eigenkapital
    # umgebuchten Gewinn-/Kapitalvortrag frueherer Jahre. Mathematisch die einzige
    # garantierte Groesse, welche die Bilanz aufgehen laesst (kein P&L-Summieren,
    # das Altgewinne doppelt zaehlen wuerde).
    gewinnvortrag_kumuliert = round(
        aktiven_total - fremdkapital_total - eigenkapital_gebucht - jahresergebnis, 2
    )
    eigenkapital_total = round(
        eigenkapital_gebucht + gewinnvortrag_kumuliert + jahresergebnis, 2
    )
    passiven_total = round(fremdkapital_total + eigenkapital_total, 2)
    # Bilanzsumme = Total Aktiven; einheitlicher Nenner fuer EK-/FK-Quote.
    bilanzsumme = aktiven_total

    return {
        "fluessige_mittel": fluessige_mittel,
        "forderungen": forderungen,
        "vorraete": vorraete,
        "aktive_abgrenzung": aktive_abgrenzung,
        "umlaufvermoegen": umlaufvermoegen,
        "anlagevermoegen": anlagevermoegen,
        "aktiven_total": aktiven_total,
        "kurzfristiges_fk": kurzfr_fk,
        "langfristiges_fk": langfr_fk,
        "fremdkapital_total": fremdkapital_total,
        "eigenkapital_gebucht": eigenkapital_gebucht,
        "gewinnvortrag_kumuliert": gewinnvortrag_kumuliert,
        "jahresergebnis_laufend": jahresergebnis,
        "eigenkapital_total": eigenkapital_total,
        "passiven_total": passiven_total,
        # Kennzahlen
        "ek_quote": _ratio_pct(eigenkapital_total, bilanzsumme),
        "fk_quote": _ratio_pct(fremdkapital_total, bilanzsumme),
        "liquiditaet_1": _ratio_pct(fluessige_mittel, kurzfr_fk),
        "liquiditaet_2": _ratio_pct(fluessige_mittel + forderungen, kurzfr_fk),
        "liquiditaet_3": _ratio_pct(umlaufvermoegen, kurzfr_fk),
        "working_capital": round(umlaufvermoegen - kurzfr_fk, 2),
        "anlagedeckungsgrad_2": _ratio_pct(
            eigenkapital_total + langfr_fk, anlagevermoegen
        ),
        # Plausibilitaet: Differenz Aktiven/Passiven (sollte ~0 sein)
        "bilanz_differenz": round(aktiven_total - passiven_total, 2),
    }


async def _compute_expenses_by_account(
    bexio: BexioClient,
    from_date: str,
    to_date: str,
    accounts_meta: dict[int, dict],
) -> dict[int, dict]:
    """Aufwand je Einzelkonto: Monatsreihe + Total ueber den Zeitraum."""
    entries = await _get_journal_data(bexio, from_date, to_date)
    per_acc: dict[int, dict] = {}
    for e in entries:
        try:
            amount = float(e.get("amount", 0))
        except (ValueError, TypeError):
            continue
        d = e.get("date") or ""
        mk = d[:7]
        if len(mk) != 7:
            continue
        for acc_id, sign in (
            (e.get("debit_account_id"), 1.0),
            (e.get("credit_account_id"), -1.0),
        ):
            if not acc_id:
                continue
            acc_no = accounts_meta.get(acc_id, {}).get("no", 0)
            if not _is_expense_account(acc_no):
                continue
            bucket = per_acc.setdefault(
                acc_id,
                {
                    "account_no": acc_no,
                    "name": accounts_meta.get(acc_id, {}).get("name", ""),
                    "category": _categorize_account(acc_no),
                    "monthly": defaultdict(float),
                    "total": 0.0,
                },
            )
            bucket["monthly"][mk] += amount * sign
            bucket["total"] += amount * sign
    return per_acc


async def _compute_bank_balance(
    bexio: BexioClient,
    bank_account_ids: set[int],
) -> float:
    """Banksaldo: Summe aller Buchungen auf Bankkonten seit Geschaeftsjahr-Beginn."""
    balances = await _compute_bank_balances_by_account(bexio, bank_account_ids)
    return sum(balances.values())


async def _compute_expenses_by_month(
    bexio: BexioClient,
    from_date: str,
    to_date: str,
    accounts_map: dict[int, int],
) -> dict[str, float]:
    """Monatliche Ausgaben: Soll-Buchungen auf Aufwandkonten abzgl. Haben-Korrekturen."""
    entries = await _get_journal_data(bexio, from_date, to_date)
    expense_account_ids = {
        acc_id for acc_id, acc_no in accounts_map.items()
        if _is_expense_account(acc_no)
    }

    expenses: dict[str, float] = defaultdict(float)
    for e in entries:
        entry_date = (e.get("date") or "")[:10]
        if len(entry_date) < 7:
            continue
        mk = entry_date[:7]
        amount = float(e.get("amount", 0))
        if e.get("debit_account_id") in expense_account_ids:
            expenses[mk] += amount
        if e.get("credit_account_id") in expense_account_ids:
            expenses[mk] -= amount

    return dict(expenses)


async def _compute_expenses_by_category(
    bexio: BexioClient,
    from_date: str,
    to_date: str,
    accounts_map: dict[int, int],
) -> dict[str, float]:
    """Ausgaben nach KMU-Kategorie: Soll abzgl. Haben-Korrekturen (Privatanteile)."""
    entries = await _get_journal_data(bexio, from_date, to_date)
    cat_totals: dict[str, float] = defaultdict(float)
    for e in entries:
        amount = float(e.get("amount", 0))
        did = e.get("debit_account_id")
        cid = e.get("credit_account_id")
        debit_no = accounts_map.get(did, 0)
        credit_no = accounts_map.get(cid, 0)
        if _is_expense_account(debit_no):
            cat_totals[_categorize_account(debit_no)] += amount
        if _is_expense_account(credit_no):
            cat_totals[_categorize_account(credit_no)] -= amount
    return dict(cat_totals)


# ── Bekannte Finanz-Konten (Sonderposten-Labels) ─────────
SPECIAL_ACCOUNT_LABELS = {
    2261: "Dividende",
    2120: "Kontokorrent GS",
    2200: "MWST-Zahlung",
    2201: "MWST-Zahlung",
    2206: "Verrechnungssteuer",
    2300: "Passive RA",
    2302: "Ferienguthaben",
    2970: "Gewinnvortrag",
    2950: "Gesetzl. Reserve",
    2270: "Sozialversicherungen",
    2271: "Pensionskasse (BVG)",
    5700: "Sozialversicherungen",
    5720: "Pensionskasse (BVG)",
    5730: "UVG / KTG",
    8900: "Direkte Steuern",
}


def _classify_bank_outflow(gegen_no: int) -> str:
    """Klassifiziert eine Bank-Auszahlung anhand des Gegenkontos.

    Returns: "invest" | "fin" | "personnel" | "social" | "pension" | "tax" | "op".

    Liquiditaets-Buckets (cash-basis), bewusst grob -- ergaenzen die
    periodengerechte Kostenstruktur um die Sicht "wann verlaesst Geld das Konto":
    - personnel: Loehne / uebriger Personalaufwand (5000-5099, 5800-5899)
    - pension:   Pensionskasse / berufliche Vorsorge BVG (Aufwand 5720-5729,
                 Kontokorrent Vorsorgeeinrichtung 2271-2279) -- klumpig, quartalsweise
    - social:    uebrige Sozialversicherungen AHV/IV/EO/ALV/FAK/UVG/KTG (Aufwand
                 5700-5719, 5730-5799, Verbindl. 2270) -- monatlich wiederkehrend
    - tax:       MWST/VST (2200-2206) und direkte Steuern (8900-8999) -- klumpig
    - fin:       echte Finanzierung (2100-2199, 2260-2269, 2400-2999, inkl. Dividende)
    - invest:    Anlagen (1500-1599)
    - op:        uebrige operative Auszahlungen (inkl. Kreditoren 2000-2099)

    Wichtig: Kreditoren-Zahlungen (2000-2099) bleiben operativ, damit normale
    Lieferantenzahlungen nicht faelschlich als Finanzierungs-Abfluss erscheinen
    und die Liquiditaetsprognose verzerren.
    """
    if 1500 <= gegen_no <= 1599:
        return "invest"
    # Echte Finanzierung: kurz-/langfristige Finanzverbindlichkeiten,
    # Kontokorrent Gesellschafter (2100-2199), beschlossene Ausschuettungen
    # (2260-2269, z. B. Dividende), langfristiges FK und Eigenkapital (2400-2999).
    # Achtung: 2271-2279 (BVG) wird unten als pension abgefangen, bevor der
    # generische 2260-2269-Finanzierungs-Check greift -- die Reihenfolge stimmt,
    # da 2271 ausserhalb von 2260-2269 liegt.
    if (2100 <= gegen_no <= 2199) or (2260 <= gegen_no <= 2269) or (2400 <= gegen_no <= 2999):
        return "fin"
    # Personal: Loehne (5000-5099) und uebriger Personalaufwand (5800-5899).
    if (5000 <= gegen_no <= 5099) or (5800 <= gegen_no <= 5899):
        return "personnel"
    # Pensionskasse / berufliche Vorsorge (BVG): Aufwand 5720-5729, Kontokorrent
    # Vorsorgeeinrichtung 2271-2279. Bewusst VOR dem social-Check, damit BVG
    # quartalsweise prognostiziert wird (nicht mit den monatlichen Sozialvers.
    # vermischt). Schweizer KMU-Kontenrahmen.
    if (5720 <= gegen_no <= 5729) or (2271 <= gegen_no <= 2279):
        return "pension"
    # Uebrige Sozialversicherungen AHV/IV/EO/ALV/FAK/UVG/KTG: Aufwand 5700-5719,
    # 5730-5799, Verbindlichkeit 2270 -- monatlich wiederkehrend.
    if (5700 <= gegen_no <= 5719) or (5730 <= gegen_no <= 5799) or (gegen_no == 2270):
        return "social"
    # MWST/Verrechnungssteuer (2200-2206) und direkte Steuern (8900-8999).
    if (2200 <= gegen_no <= 2206) or (8900 <= gegen_no <= 8999):
        return "tax"
    # Operative Verbindlichkeiten: Kreditoren (2000-2099) und Rest.
    return "op"


async def _compute_categorized_cashflow(
    bexio: BexioClient,
    bank_account_ids: set[int],
    from_date: str,
    to_date: str,
    accounts_map: dict[int, int],
) -> dict[str, dict]:
    """Kategorisierter Cashflow pro Monat aus Bankkonten (direkte Methode).

    Jede Bankbuchung wird anhand des Gegenkontos via _classify_bank_outflow
    klassifiziert:
    - investiv (Anlagen 1500-1599)
    - Finanzierung (echte Finanzverbindl./EK: 2100-2199, 2260-2269, 2400-2999)
    - operativ (Rest, inkl. Kreditoren 2000-2099 und MWST/Steuern 2200-2399)
    """
    entries = await _get_journal_data(bexio, from_date, to_date)
    flows: dict[str, dict] = defaultdict(lambda: {
        "inflow": 0.0, "op_outflow": 0.0,
        "personnel_outflow": 0.0, "social_outflow": 0.0, "pension_outflow": 0.0,
        "tax_outflow": 0.0,
        "fin_outflow": 0.0, "invest_outflow": 0.0,
        "special_items": defaultdict(float),
    })

    for e in entries:
        mk = (e.get("date") or "")[:7]
        if not mk:
            continue
        amount = float(e.get("amount", 0))
        did = e.get("debit_account_id")
        cid = e.get("credit_account_id")

        if did in bank_account_ids:
            flows[mk]["inflow"] += amount

        if cid in bank_account_ids:
            gegen_no = accounts_map.get(did, 0)
            kind = _classify_bank_outflow(gegen_no)
            if kind == "invest":
                flows[mk]["invest_outflow"] += amount
            elif kind == "fin":
                flows[mk]["fin_outflow"] += amount
                label = SPECIAL_ACCOUNT_LABELS.get(gegen_no, f"Kto {gegen_no}")
                flows[mk]["special_items"][label] += amount
            elif kind == "personnel":
                flows[mk]["personnel_outflow"] += amount
            elif kind == "social":
                flows[mk]["social_outflow"] += amount
                label = SPECIAL_ACCOUNT_LABELS.get(gegen_no, f"Kto {gegen_no}")
                flows[mk]["special_items"][label] += amount
            elif kind == "pension":
                flows[mk]["pension_outflow"] += amount
                label = SPECIAL_ACCOUNT_LABELS.get(gegen_no, f"Kto {gegen_no}")
                flows[mk]["special_items"][label] += amount
            elif kind == "tax":
                flows[mk]["tax_outflow"] += amount
                label = SPECIAL_ACCOUNT_LABELS.get(gegen_no, f"Kto {gegen_no}")
                flows[mk]["special_items"][label] += amount
            else:
                flows[mk]["op_outflow"] += amount

    result = {}
    for mk, data in flows.items():
        items = [
            {"label": label, "amount": round(amt, 2)}
            for label, amt in sorted(data["special_items"].items(), key=lambda x: -x[1])
            if amt > 100
        ]
        result[mk] = {
            "inflow": round(data["inflow"], 2),
            "op_outflow": round(data["op_outflow"], 2),
            "personnel_outflow": round(data["personnel_outflow"], 2),
            "social_outflow": round(data["social_outflow"], 2),
            "pension_outflow": round(data["pension_outflow"], 2),
            "tax_outflow": round(data["tax_outflow"], 2),
            "fin_outflow": round(data["fin_outflow"], 2),
            "invest_outflow": round(data["invest_outflow"], 2),
            "special_items": items,
        }
    return result


# ── Response-Modelle ─────────────────────────────────────

class CashflowSpecialItem(BaseModel):
    label: str
    amount: float


class KpiOverview(BaseModel):
    bank_balance: float | None = None
    bank_account_name: str | None = None
    open_invoices_total: float = 0
    open_invoices_count: int = 0
    current_month_revenue: float = 0
    current_month_hours: float = 0
    forecast_year_revenue: float = 0
    forecast_year_revenue_runrate: float = 0   # erwartet: gesichert + Auffuellung (Run-Rate)
    forecast_year_end_cashflow: float = 0
    forecast_year_end_runrate: float = 0   # Vergleichsszenario (Run-Rate gehalten)
    revenue_gap_to_goal: float = 0         # noch fehlender Umsatz bis Jahresziel
    annual_revenue_goal: float = 0
    min_liquidity: float = 0
    burn_rate: float = 0
    runway_months: float | None = None
    runway_months_incl_debtors: float | None = None
    profit_margin_ytd: float | None = None
    revenue_ytd: float = 0              # Live (= revenue_ytd_live), Karten-Hauptwert
    revenue_ytd_live: float = 0         # abgeschl. Monate + geschätzter laufender Monat
    revenue_ytd_closed: float = 0       # nur abgeschlossene Monate (faire Basis)
    revenue_ytd_net: float = 0          # netto auf Live-Basis
    revenue_ytd_net_closed: float = 0   # netto auf abgeschlossener Basis (Ratios)
    expenses_ytd: float = 0
    expenses_ytd_closed: float = 0
    profit_ytd: float | None = None
    closed_until_month: int = 0         # letzter abgeschlossener Monat (1-12, 0 = keiner)
    closed_until_label: str = ""        # z.B. "Mai"
    ebitda_ytd: float | None = None
    personalquote_ytd: float | None = None
    personnel_cost_ytd: float | None = None
    personnel_cost_annualized: float | None = None
    dso_days: float | None = None
    liquiditaet_2: float | None = None
    ek_quote: float | None = None
    revenue_ytd_prior: float = 0
    prior_year_revenue: float = 0       # Vorjahres-Gesamtumsatz (brutto, alle 12 Monate)
    expenses_ytd_prior: float = 0
    ebitda_ytd_prior: float | None = None
    personalquote_ytd_prior: float | None = None
    profit_margin_ytd_prior: float | None = None
    journal_data_from: str | None = None
    journal_data_to: str | None = None
    as_of_date: str = ""               # Stichtag der YTD-Kennzahlen (heute)
    vat_method: str = "saldo"          # angewandte MWST-Methode (saldo/effektiv/none)
    vat_saldo_rate: float | None = None  # Saldosteuersatz (nur bei method=saldo)
    vat_rate: float = 0.081            # Fakturierungssatz (Normalsatz)
    currency: str = "CHF"


class CashflowMonth(BaseModel):
    month: str
    revenue: float = 0
    expenses: float = 0                # Übrige operative Auszahlungen (Rest)
    personnel_outflow: float = 0       # Löhne / übriger Personalaufwand
    social_outflow: float = 0          # Sozialversicherungen AHV/IV/EO/ALV/FAK/UVG/KTG (monatlich)
    pension_outflow: float = 0         # Pensionskasse / BVG (quartalsweise)
    tax_outflow: float = 0             # MWST / direkte Steuern (klumpig)
    fin_outflow: float = 0
    invest_outflow: float = 0
    delta: float = 0
    cumulative: float = 0
    cumulative_expected: float = 0   # Saldo im erwarteten (Run-Rate) Szenario
    is_forecast: bool = False
    special_items: list[CashflowSpecialItem] = []
    # Aufschluesselung der Einnahmen-Prognose (nur bei is_forecast befuellt, brutto)
    forecast_committed: float = 0   # gebuchte Kapazitaet (bestaetigt)
    forecast_pipeline: float = 0    # gewichtete Pipeline (vorlaeufig)
    forecast_fill: float = 0        # Run-Rate-Auffuellung zur Baseline


class CapacityForecastMonth(BaseModel):
    month: str
    revenue: float = 0
    hours: float = 0


class CashflowResponse(BaseModel):
    months: list[CashflowMonth]
    forecast_revenue_monthly: float = 0   # Run-Rate (Ø), Referenzlinie
    forecast_expenses_monthly: float = 0
    start_balance: float = 0
    capacity_forecast: list[CapacityForecastMonth] = []
    # Ziel-/Schwellenwerte fuer die Referenzlinien (brutto, CHF)
    annual_revenue_goal: float = 0
    monthly_revenue_goal: float = 0
    min_liquidity: float = 0


class TogglProjectSummary(BaseModel):
    project_name: str
    client_name: str = ""
    hours: float = 0
    rate_per_hour: float = 0
    amount: float = 0
    currency: str = "CHF"


class ExpenseCategoryResponse(BaseModel):
    categories: list["ExpenseCategory"]
    period_from: str = ""
    period_to: str = ""
    months_covered: int = 0


class ExpenseCategory(BaseModel):
    key: str
    label: str
    account_range: str
    monthly_average: float = 0
    total_12m: float = 0
    recurrence: str = "unbekannt"


class YoyMonth(BaseModel):
    month_label: str
    month_num: int
    revenue_current: float = 0
    revenue_prior: float = 0
    expenses_current: float = 0
    expenses_prior: float = 0


class YoyResponse(BaseModel):
    current_year: int
    prior_year: int
    months: list[YoyMonth]
    revenue_current_ytd: float = 0
    revenue_prior_ytd: float = 0
    growth_pct: float | None = None
    as_of_date: str = ""            # Stichtag des Vergleichs (heute)
    compare_until_month: int = 0    # letzter vollständig verglichener Monat (1-12)
    compare_until_label: str = ""   # z.B. "Mai" -- Vergleich bis und mit diesem Monat


class WaterfallStep(BaseModel):
    label: str
    value: float
    step_type: str  # "income", "expense", "total"


class WaterfallResponse(BaseModel):
    steps: list[WaterfallStep]
    period_label: str
    revenue_total: float = 0
    expenses_total: float = 0
    result: float = 0


class BalanceSheetResponse(BaseModel):
    # Aktiven
    fluessige_mittel: float = 0
    forderungen: float = 0
    vorraete: float = 0
    aktive_abgrenzung: float = 0
    umlaufvermoegen: float = 0
    anlagevermoegen: float = 0
    aktiven_total: float = 0
    # Passiven
    kurzfristiges_fk: float = 0
    langfristiges_fk: float = 0
    fremdkapital_total: float = 0
    eigenkapital_gebucht: float = 0
    gewinnvortrag_kumuliert: float = 0
    jahresergebnis_laufend: float = 0
    eigenkapital_total: float = 0
    passiven_total: float = 0
    # Kennzahlen
    ek_quote: float | None = None
    fk_quote: float | None = None
    liquiditaet_1: float | None = None
    liquiditaet_2: float | None = None
    liquiditaet_3: float | None = None
    working_capital: float = 0
    anlagedeckungsgrad_2: float | None = None
    bilanz_differenz: float = 0
    period_from: str = ""
    period_to: str = ""
    currency: str = "CHF"


class ExpenseAccountItem(BaseModel):
    account_no: int
    name: str
    category: str
    category_label: str = ""
    total: float = 0          # Summe ueber den Zeitraum
    total_ytd: float = 0      # Summe laufendes Jahr
    monthly_avg_12m: float = 0
    monthly: dict[str, float] = {}


class ExpensesByAccountResponse(BaseModel):
    accounts: list[ExpenseAccountItem]
    total: float = 0
    total_ytd: float = 0
    period_from: str = ""
    period_to: str = ""
    months_covered: int = 0
    currency: str = "CHF"


# ── Endpoints ────────────────────────────────────────────

@router.get("/overview", response_model=KpiOverview)
async def get_overview(user: User = Depends(require_role("owner"))):
    """KPI-Uebersicht mit Jahresprognosen, Burn Rate und Runway."""
    cached = _overview_cache.get("overview")
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    today = date.today()
    current_year = today.year
    current_month = _month_key(today)

    # ── Stichtag-Logik: laufender Monat ist wegen Monatsend-Fakturierung
    # unvollständig. Für faire Vergleiche zählen nur abgeschlossene Monate
    # (Jan bis und mit Vormonat). Der laufende Monat wird separat geschätzt.
    prior_year = current_year - 1
    last_complete_month_num = today.month - 1  # 0 im Januar (keine abgeschl. Monate)
    _month_names = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    closed_until_label = (
        _month_names[last_complete_month_num]
        if 1 <= last_complete_month_num <= 12 else ""
    )
    current_closed_key = (
        f"{current_year}-{last_complete_month_num:02d}"
        if last_complete_month_num >= 1 else None
    )
    prior_closed_key = (
        f"{prior_year}-{last_complete_month_num:02d}"
        if last_complete_month_num >= 1 else None
    )
    # Letzter Tag des letzten abgeschlossenen Monats (für Journal-/Kategorie-Abfragen)
    closed_to_date = (today.replace(day=1) - timedelta(days=1)).isoformat()
    # Gleicher Stichtag im Vorjahr (für stichtagsgleiche Vergleiche)
    prior_closed_to_date = (
        (date(prior_year, last_complete_month_num + 1, 1) - timedelta(days=1)).isoformat()
        if 1 <= last_complete_month_num <= 11 else
        (f"{prior_year}-12-31" if last_complete_month_num == 12 else None)
    )

    # Banksaldo via Journal
    bank_balance = None
    bank_name = None
    bank_ids: set[int] = set()
    try:
        bank_accounts = await bexio.list_bank_accounts()
        if bank_accounts:
            bank_ids = {a.get("account_id") for a in bank_accounts if a.get("account_id")}
            if bank_ids:
                balances_by_account = await _compute_bank_balances_by_account(bexio, bank_ids)
                bank_balance = sum(balances_by_account.values())
                # Namen des tatsaechlich genutzten Kontos (groesster Saldo) anzeigen --
                # nicht stur das erste Konto (sonst erscheinen alte, inaktive Konten).
                id_to_name = {
                    a.get("account_id"): a.get("name")
                    for a in bank_accounts if a.get("account_id")
                }
                active_ids = [aid for aid, bal in balances_by_account.items() if abs(bal) > 0.005]
                if active_ids:
                    dominant_id = max(active_ids, key=lambda aid: abs(balances_by_account[aid]))
                    bank_name = id_to_name.get(dominant_id) or "Hauptkonto"
                    if len(active_ids) > 1:
                        bank_name = f"{bank_name} (+{len(active_ids) - 1} weitere)"
                else:
                    bank_name = bank_accounts[0].get("name", "Hauptkonto")
    except Exception as e:
        logger.warning("Banksaldo nicht verfuegbar: %s", e)

    # Rechnungen laden (25 Monate fuer YTD + Prognose-Basis)
    all_invoices: list[dict] = []
    try:
        all_invoices = await _fetch_recent_invoices(bexio, months=25)
    except Exception as e:
        logger.warning("Rechnungen nicht verfuegbar: %s", e)

    # Offene Debitoren
    open_total = 0.0
    open_count = 0
    for inv in all_invoices:
        if _invoice_is_open(inv):
            remaining = inv.get("total_remaining_payments")
            if remaining is not None:
                try:
                    open_total += float(remaining)
                except (ValueError, TypeError):
                    open_total += _parse_bexio_invoice_total(inv)
            else:
                open_total += _parse_bexio_invoice_total(inv)
            open_count += 1

    # Revenue by month
    revenue_by_month = _revenue_by_month_from_invoices(all_invoices)

    # YTD Revenue (faire Basis): nur abgeschlossene Monate, stichtagsgleich VJ.
    revenue_ytd_closed = sum(
        v for mk, v in revenue_by_month.items()
        if current_closed_key and mk.startswith(str(current_year)) and mk <= current_closed_key
    )
    revenue_ytd_closed_prior = sum(
        v for mk, v in revenue_by_month.items()
        if prior_closed_key and mk.startswith(str(prior_year)) and mk <= prior_closed_key
    )
    # Vorjahres-Gesamtumsatz (brutto, alle 12 Monate) -- fuer den VJ-Vergleich der
    # Jahresumsatz-Prognose. Der 25-Monats-Lookback deckt das ganze Vorjahr ab.
    prior_year_revenue = sum(
        v for mk, v in revenue_by_month.items() if mk.startswith(str(prior_year))
    )

    # Ausgaben
    accounts_map: dict[int, int] = {}
    expenses_by_month: dict[str, float] = {}
    journal_from = f"{current_year - 1}-01-01"
    try:
        accounts_map = await _get_accounts_map(bexio)
        expenses_by_month = await _compute_expenses_by_month(
            bexio, journal_from, today.isoformat(), accounts_map
        )
    except Exception as e:
        logger.warning("Ausgaben nicht verfuegbar: %s", e)

    # Kategorisierter Cashflow (fuer klumpige Finanz-/Investitionsabfluesse)
    cat_cf: dict[str, dict] = {}
    try:
        if bank_ids and accounts_map:
            cat_cf = await _compute_categorized_cashflow(
                bexio, bank_ids, journal_from, today.isoformat(), accounts_map
            )
    except Exception as e:
        logger.warning("Kategorisierter Cashflow (Overview) nicht verfuegbar: %s", e)

    # Toggl: laufender Monat (frueh geladen, damit die Jahresprognose ihn nutzen kann)
    current_revenue = 0.0
    current_hours = 0.0
    try:
        toggl = _get_toggl_client(user)
        start = today.replace(day=1).isoformat()
        end = today.isoformat()
        summary = await toggl.get_summary_by_project(start, end, billable=True)
        current_revenue, current_hours = _parse_toggl_revenue(summary)
    except Exception as e:
        logger.warning("Toggl-Summary nicht verfuegbar: %s", e)

    # Prognose-Basis (letzte 3 und 12 Monate) -- nur abgeschlossene Monate
    hist_months_12 = _month_range(12, 0)[:-1]
    hist_months_3 = hist_months_12[-3:] if len(hist_months_12) >= 3 else hist_months_12
    rev_3m = [revenue_by_month.get(m, 0) for m in hist_months_3 if m < current_month]
    rev_12m = [revenue_by_month.get(m, 0) for m in hist_months_12 if m < current_month]
    exp_3m = [expenses_by_month.get(m, 0) for m in hist_months_3 if m < current_month]
    exp_12m = [expenses_by_month.get(m, 0) for m in hist_months_12 if m < current_month]

    forecast_rev = _weighted_forecast(rev_3m, rev_12m)
    forecast_exp = _weighted_forecast(exp_3m, exp_12m)

    # Klumpige Kategorien ueber 12 Monate amortisieren (konsistent zum Cashflow-Chart)
    fin_12m = [cat_cf.get(m, {}).get("fin_outflow", 0) for m in hist_months_12 if m < current_month]
    inv_12m = [cat_cf.get(m, {}).get("invest_outflow", 0) for m in hist_months_12 if m < current_month]
    forecast_fin = _trailing_12m_avg(fin_12m)
    forecast_inv = _trailing_12m_avg(inv_12m)

    # Operativer CASH-Abfluss (Bankbewegungen) -- Basis fuer die Liquiditaetsprognose.
    # Bewusst getrennt vom accrualen forecast_exp (Aufwandskonten), das fuer P&L-KPIs
    # (EBITDA, Personalquote, Marge) verwendet wird.
    op_cash_3m = [cat_cf.get(m, {}).get("op_outflow", 0) for m in hist_months_3 if m < current_month]
    op_cash_12m = [cat_cf.get(m, {}).get("op_outflow", 0) for m in hist_months_12 if m < current_month]
    forecast_op_cash = _weighted_forecast(op_cash_3m, op_cash_12m)
    # Personal (monatlich) sowie klumpige Buckets (Sozial/BVG, MWST/Steuern) als
    # 12M-amortisierter Monats-Schnitt -- damit die Jahresend-Liquiditaet alle
    # Auszahlungen enthaelt und konsistent zur Cashflow-Tabelle bleibt.
    forecast_personnel_cash = _trailing_12m_avg(
        [cat_cf.get(m, {}).get("personnel_outflow", 0) for m in hist_months_12 if m < current_month]
    )
    forecast_social_cash = _trailing_12m_avg(
        [cat_cf.get(m, {}).get("social_outflow", 0) for m in hist_months_12 if m < current_month]
    )
    # Pensionskasse/BVG seit dem Split eigenes Bucket -- muss separat in die
    # Jahresend-Liquiditaet einfliessen, sonst sinkt die KPI faelschlich.
    forecast_pension_cash = _trailing_12m_avg(
        [cat_cf.get(m, {}).get("pension_outflow", 0) for m in hist_months_12 if m < current_month]
    )
    forecast_tax_cash = _trailing_12m_avg(
        [cat_cf.get(m, {}).get("tax_outflow", 0) for m in hist_months_12 if m < current_month]
    )

    # Fix 1: Laufender Monat -- Prognose-Ausgaben wenn Journal noch leer
    actual_current_exp = expenses_by_month.get(current_month, 0)
    if today.day <= 15 and actual_current_exp < forecast_exp * 0.5:
        current_month_exp = forecast_exp
    else:
        current_month_exp = actual_current_exp

    # YTD Expenses: abgeschlossene Monate (faire Basis) + korrigierter laufender Monat (live)
    expenses_ytd_closed = sum(
        v for mk, v in expenses_by_month.items()
        if mk.startswith(str(current_year)) and mk < current_month
    )
    expenses_ytd = expenses_ytd_closed + current_month_exp

    # Burn Rate = durchschnittliche monatliche Ausgaben
    burn_rate = forecast_exp

    # Runway
    runway_months = None
    runway_months_incl_debtors = None
    if bank_balance is not None and burn_rate > 0:
        runway_months = round(bank_balance / burn_rate, 1)
        runway_months_incl_debtors = round((bank_balance + open_total) / burn_rate, 1)

    # Jahresprognose (konsistent mit dem Cashflow-Layer-Modell)
    fs = get_forecast_settings_from_settings(user.settings)
    mwst_satz = fs.vat_rate
    vat_factor = 1 + mwst_satz
    months_elapsed = today.month
    months_remaining = 12 - months_elapsed

    # Restmonate (nach dem laufenden Monat) + laufender Monat via Kapazitaet
    year_keys = [current_month] + [f"{current_year}-{m:02d}" for m in range(months_elapsed + 1, 13)]
    cap_year = await _compute_capacity_monthly(user, year_keys, fs) if year_keys else {}

    # Laufender Monat: gebuchte Kapazitaet vs. bereits fakturiert/erfasst (brutto), max
    cap_cur = cap_year.get(current_month, {})
    cur_booked = (
        cap_cur.get("committed_net", 0.0) * vat_factor
        + cap_cur.get("pipeline_net", 0.0) * vat_factor * fs.pipeline_weight
    )
    cur_actual_gross = max(revenue_by_month.get(current_month, 0.0), current_revenue * vat_factor)
    current_month_revenue_proj = max(cur_actual_gross, cur_booked)

    remaining_keys = [f"{current_year}-{m:02d}" for m in range(months_elapsed + 1, 13)]
    forecast_remaining_secured = 0.0   # gebucht + gewichtete Pipeline (konsistent zu Balken)
    forecast_remaining_runrate = 0.0   # Vergleichsszenario: bei gehaltener Run-Rate
    for k, mk in enumerate(remaining_keys, start=1):
        cap = cap_year.get(mk, {})
        committed_gross = cap.get("committed_net", 0.0) * vat_factor
        pipeline_gross = cap.get("pipeline_net", 0.0) * vat_factor * fs.pipeline_weight
        booked = committed_gross + pipeline_gross
        forecast_remaining_secured += booked
        fill = min(1.0, k / fs.fill_horizon_months) if fs.fill_horizon_months > 0 else 1.0
        forecast_remaining_runrate += booked + max(0.0, forecast_rev - booked) * fill

    # Abgeschlossene Monate (Ist) + laufender Monat (projiziert) + Restmonate (gesichert)
    revenue_completed = sum(
        v for mk, v in revenue_by_month.items()
        if mk.startswith(str(current_year)) and mk < current_month
    )
    forecast_year_revenue = revenue_completed + current_month_revenue_proj + forecast_remaining_secured
    # Erwarteter Jahresumsatz: gesicherte Basis + erwartete Auffuellung der noch
    # unverkauften Kapazitaet (Run-Rate-Szenario, Ø 3/12 Mt.).
    forecast_year_revenue_runrate = (
        revenue_completed + current_month_revenue_proj + forecast_remaining_runrate
    )
    # Liquiditaetsprognose per 31.12. = heutiger Banksaldo + kuenftige Netto-Cashflows.
    # Gesichertes Szenario (gebucht + Pipeline), operative Kosten als CASH (Bank-Abfluss),
    # identisch zur Cashflow-Tabelle -- die KPI entspricht exakt der Dezember-Zeile "Kum. Saldo".
    monthly_cash_out = (
        forecast_op_cash + forecast_personnel_cash + forecast_social_cash
        + forecast_pension_cash + forecast_tax_cash + forecast_fin + forecast_inv
    )
    forecast_year_end_cashflow = (
        (bank_balance or 0)
        + forecast_remaining_secured
        - months_remaining * monthly_cash_out
    )
    # Vergleichsszenario: bei gehaltener Run-Rate (zusaetzlich akquiriertes Geschaeft)
    forecast_year_end_runrate = (
        (bank_balance or 0)
        + forecast_remaining_runrate
        - months_remaining * monthly_cash_out
    )
    # Noch fehlender Umsatz bis zum Jahresziel (brutto)
    revenue_gap_to_goal = (
        max(0.0, fs.annual_revenue_goal - forecast_year_revenue)
        if fs.annual_revenue_goal > 0 else 0.0
    )

    # ── Live-Sicht vs. faire Vergleichsbasis ────────────────
    # Live (Karten-Hauptwert): abgeschlossene Monate + geschätzter laufender Monat
    # (Kapazität früh im Monat, Toggl-Ist im Verlauf -- current_month_revenue_proj).
    revenue_ytd_live = revenue_ytd_closed + current_month_revenue_proj
    revenue_ytd_net = fs.net_revenue(revenue_ytd_live)            # Live, für Karten
    revenue_ytd_net_closed = fs.net_revenue(revenue_ytd_closed)   # faire Basis, für Ratios

    # Gewinn/Marge YTD auf fairer Basis (abgeschlossene Monate, netto)
    profit_ytd = round(revenue_ytd_net_closed - expenses_ytd_closed, 2)
    profit_margin_ytd = None
    if revenue_ytd_net_closed > 0:
        profit_margin_ytd = round(
            (revenue_ytd_net_closed - expenses_ytd_closed) / revenue_ytd_net_closed * 100, 1
        )

    # EBITDA + Personalquote YTD (faire Basis): nur bis Ende letzter abgeschlossener Monat
    ebitda_ytd = None
    personalquote_ytd = None
    personnel_cost_ytd = None
    personnel_cost_annualized = None
    if current_closed_key:
        try:
            cat_ytd = await _compute_expenses_by_category(
                bexio, f"{current_year}-01-01", closed_to_date, accounts_map
            )
            non_ebitda_cats = {"abschreibungen", "finanzaufwand", "steuern", "ausserordentlich"}
            operating_exp = sum(v for k, v in cat_ytd.items() if k not in non_ebitda_cats)
            ebitda_ytd = round(revenue_ytd_net_closed - operating_exp, 2)

            personal_cats = {"loehne", "sozialversicherungen", "pensionskasse", "uvg_ktg",
                             "spesen_personal", "personalaufwand_sonstig", "uebr_personal"}
            personal_total = sum(v for k, v in cat_ytd.items() if k in personal_cats)
            personnel_cost_ytd = round(personal_total, 2)
            # Jahres-Hochrechnung auf Basis abgeschlossener Monate (robust, da
            # die Lohnbuchung des laufenden Monats oft noch fehlt).
            if last_complete_month_num >= 1:
                personnel_cost_annualized = round(
                    personal_total / last_complete_month_num * 12, 2
                )
            if revenue_ytd_net_closed > 0:
                personalquote_ytd = round(personal_total / revenue_ytd_net_closed * 100, 1)
        except Exception:
            pass

    # DSO (Days Sales Outstanding): Offene Debitoren / Tagesumsatz (abgeschlossene Monate)
    dso_days = None
    if revenue_ytd_closed > 0 and last_complete_month_num >= 1:
        daily_rev = revenue_ytd_closed / (last_complete_month_num * 30)
        if daily_rev > 0:
            dso_days = round(open_total / daily_rev, 0)

    # Liquiditaetsgrad 2 + EK-Quote aus der Saldenbilanz (Journal-basiert)
    liquiditaet_2 = None
    ek_quote = None
    try:
        if accounts_map:
            bs = await _compute_balance_sheet(bexio, accounts_map)
            liquiditaet_2 = bs.get("liquiditaet_2")
            ek_quote = bs.get("ek_quote")
    except Exception as e:  # noqa: BLE001
        logger.warning("Bilanzkennzahlen (Overview) nicht verfuegbar: %s", e)

    # ── Vorjahres-KPIs (stichtagsgleich: gleiche abgeschlossene Monate) ──
    revenue_ytd_prior = revenue_ytd_closed_prior

    expenses_ytd_prior = 0.0
    if prior_closed_to_date:
        try:
            prior_expenses = await _compute_expenses_by_month(
                bexio, f"{prior_year}-01-01", prior_closed_to_date, accounts_map
            )
            expenses_ytd_prior = sum(prior_expenses.values())
        except Exception:
            pass

    revenue_ytd_net_prior = fs.net_revenue(revenue_ytd_prior)
    profit_margin_ytd_prior = None
    if revenue_ytd_net_prior > 0:
        profit_margin_ytd_prior = round(
            (revenue_ytd_net_prior - expenses_ytd_prior) / revenue_ytd_net_prior * 100, 1
        )

    ebitda_ytd_prior = None
    personalquote_ytd_prior = None
    if prior_closed_to_date:
        try:
            cat_prior = await _compute_expenses_by_category(
                bexio, f"{prior_year}-01-01", prior_closed_to_date, accounts_map
            )
            non_ebitda_cats = {"abschreibungen", "finanzaufwand", "steuern", "ausserordentlich"}
            op_exp_prior = sum(v for k, v in cat_prior.items() if k not in non_ebitda_cats)
            ebitda_ytd_prior = round(revenue_ytd_net_prior - op_exp_prior, 2)

            personal_cats = {"loehne", "sozialversicherungen", "pensionskasse", "uvg_ktg",
                             "spesen_personal", "personalaufwand_sonstig", "uebr_personal"}
            personal_prior = sum(v for k, v in cat_prior.items() if k in personal_cats)
            if revenue_ytd_net_prior > 0:
                personalquote_ytd_prior = round(personal_prior / revenue_ytd_net_prior * 100, 1)
        except Exception:
            pass

    # Journal-Datenstand ermitteln
    journal_from_str = None
    journal_to_str = None
    try:
        all_dates = [
            (e.get("date") or "")[:10]
            for e in await _get_journal_data(bexio, f"{current_year - 1}-01-01", today.isoformat())
            if e.get("date")
        ]
        if all_dates:
            journal_from_str = min(all_dates)
            journal_to_str = max(all_dates)
    except Exception:
        pass

    result = KpiOverview(
        bank_balance=round(bank_balance, 2) if bank_balance is not None else None,
        bank_account_name=bank_name,
        open_invoices_total=round(open_total, 2),
        open_invoices_count=open_count,
        current_month_revenue=round(current_revenue, 2),
        current_month_hours=round(current_hours, 2),
        forecast_year_revenue=round(forecast_year_revenue, 2),
        forecast_year_revenue_runrate=round(forecast_year_revenue_runrate, 2),
        forecast_year_end_cashflow=round(forecast_year_end_cashflow, 2),
        forecast_year_end_runrate=round(forecast_year_end_runrate, 2),
        revenue_gap_to_goal=round(revenue_gap_to_goal, 2),
        annual_revenue_goal=round(fs.annual_revenue_goal, 2),
        min_liquidity=round(fs.min_liquidity, 2),
        burn_rate=round(burn_rate, 2),
        runway_months=runway_months,
        runway_months_incl_debtors=runway_months_incl_debtors,
        profit_margin_ytd=profit_margin_ytd,
        revenue_ytd=round(revenue_ytd_live, 2),
        revenue_ytd_live=round(revenue_ytd_live, 2),
        revenue_ytd_closed=round(revenue_ytd_closed, 2),
        revenue_ytd_net=revenue_ytd_net,
        revenue_ytd_net_closed=revenue_ytd_net_closed,
        expenses_ytd=round(expenses_ytd, 2),
        expenses_ytd_closed=round(expenses_ytd_closed, 2),
        profit_ytd=profit_ytd,
        closed_until_month=last_complete_month_num if last_complete_month_num >= 1 else 0,
        closed_until_label=closed_until_label,
        ebitda_ytd=ebitda_ytd,
        personalquote_ytd=personalquote_ytd,
        personnel_cost_ytd=personnel_cost_ytd,
        personnel_cost_annualized=personnel_cost_annualized,
        dso_days=dso_days,
        liquiditaet_2=liquiditaet_2,
        ek_quote=ek_quote,
        revenue_ytd_prior=round(revenue_ytd_prior, 2),
        prior_year_revenue=round(prior_year_revenue, 2),
        expenses_ytd_prior=round(expenses_ytd_prior, 2),
        ebitda_ytd_prior=ebitda_ytd_prior,
        personalquote_ytd_prior=personalquote_ytd_prior,
        profit_margin_ytd_prior=profit_margin_ytd_prior,
        journal_data_from=journal_from_str,
        journal_data_to=journal_to_str,
        as_of_date=today.isoformat(),
        vat_method=fs.vat_method,
        vat_saldo_rate=fs.vat_saldo_rate if fs.vat_method == "saldo" else None,
        vat_rate=fs.vat_rate,
    )
    _overview_cache["overview"] = result
    return result


@router.get("/cashflow", response_model=CashflowResponse)
async def get_cashflow(
    months_back: int = Query(default=6, ge=1, le=24),
    months_forward: int = Query(default=12, ge=1, le=24),
    user: User = Depends(require_role("owner")),
):
    """Cashflow nach direkter Methode (Swiss GAAP FER / OR).

    Alle Bankbewegungen werden nach Gegenkonto kategorisiert:
    - Operativ (Ertrags-/Aufwandkonten 3xxx-8xxx)
    - Investitionen (Anlagen 15xx)
    - Finanzierung (FK/EK 2xxx, inkl. Dividende, Kontokorrent, MWST)
    """
    cache_key = f"cashflow:{months_back}:{months_forward}"
    cached = _cashflow_cache.get(cache_key)
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    today = date.today()
    current_month = _month_key(today)
    all_month_keys = _month_range(months_back, months_forward)
    lookback = max(months_back, 12) + 1

    # Bankkonten ermitteln
    bank_ids: set[int] = set()
    start_balance = 0.0
    try:
        bank_accounts = await bexio.list_bank_accounts()
        bank_ids = {a.get("account_id") for a in bank_accounts if a.get("account_id")}
        if bank_ids:
            start_balance = await _compute_bank_balance(bexio, bank_ids)
    except Exception as e:
        logger.warning("Bankkonten nicht verfuegbar: %s", e)

    # Rechnungsdaten fuer Prognose-Basis
    revenue_by_month: dict[str, float] = defaultdict(float)
    try:
        invoices = await _fetch_recent_invoices(bexio, months=lookback)
        revenue_by_month = defaultdict(float, _revenue_by_month_from_invoices(invoices))
    except Exception as e:
        logger.warning("Rechnungen fuer Cashflow nicht verfuegbar: %s", e)

    # Kontenplan und kategorisierter Cashflow
    accounts_map: dict[int, int] = {}
    cat_cf: dict[str, dict] = {}
    try:
        accounts_map = await _get_accounts_map(bexio)
        journal_from = (today.replace(day=1) - timedelta(days=30 * lookback)).strftime("%Y-%m-%d")
        cat_cf = await _compute_categorized_cashflow(
            bexio, bank_ids, journal_from, today.isoformat(), accounts_map
        )
    except Exception as e:
        logger.warning("Kategorisierter Cashflow nicht verfuegbar: %s", e)

    # Toggl fuer laufenden Monat
    current_toggl_revenue = 0.0
    try:
        toggl = _get_toggl_client(user)
        start = today.replace(day=1).isoformat()
        end = today.isoformat()
        summary = await toggl.get_summary_by_project(start, end, billable=True)
        current_toggl_revenue, _ = _parse_toggl_revenue(summary)
    except Exception:
        pass

    # Prognose-Basis (abgeschlossene Monate)
    hist_months_12 = _month_range(12, 0)[:-1]
    hist_months_3 = hist_months_12[-3:] if len(hist_months_12) >= 3 else hist_months_12

    rev_3m = [revenue_by_month.get(m, 0) for m in hist_months_3 if m < current_month]
    rev_12m = [revenue_by_month.get(m, 0) for m in hist_months_12 if m < current_month]

    # ── Kostenseite: Buckets nach Charakter prognostizieren ──────────────
    # Monatlich wiederkehrend (Personal, Uebrige operativ) -> Run-Rate (12M-Schnitt).
    personnel_12m = [cat_cf.get(m, {}).get("personnel_outflow", 0) for m in hist_months_12 if m < current_month]
    op_12m = [cat_cf.get(m, {}).get("op_outflow", 0) for m in hist_months_12 if m < current_month]
    forecast_personnel = _trailing_12m_avg(personnel_12m)
    forecast_op = _trailing_12m_avg(op_12m)
    # Frueh-im-Monat-Fallback fuer die monatlich wiederkehrenden Kosten zusammen.
    forecast_monthly_op = forecast_personnel + forecast_op

    # Finanzierungs- und Investitionsabfluesse fuer Prognose (klumpig -> 12M-amortisiert)
    fin_12m = [cat_cf.get(m, {}).get("fin_outflow", 0) for m in hist_months_12 if m < current_month]
    inv_12m = [cat_cf.get(m, {}).get("invest_outflow", 0) for m in hist_months_12 if m < current_month]

    forecast_rev = _weighted_forecast(rev_3m, rev_12m)
    forecast_fin = _trailing_12m_avg(fin_12m)
    forecast_inv = _trailing_12m_avg(inv_12m)

    # ── Kapazitaets-Schichten fuer die Einnahmen-Prognose laden ──
    fs = get_forecast_settings_from_settings(user.settings)

    # Klumpige, termingebundene Buckets (MWST, Pensionskasse) saisonal am
    # Faelligkeitstermin platzieren statt mitteln -- so bleiben Spitzen sichtbar.
    # Sozialversicherungen sind dagegen monatlich wiederkehrend -> Run-Rate.
    forecast_months = [m for m in all_month_keys if m > current_month]
    hist_all = sorted(m for m in cat_cf.keys() if m < current_month)
    pension_hist = {m: cat_cf[m].get("pension_outflow", 0) for m in hist_all}
    tax_hist = {m: cat_cf[m].get("tax_outflow", 0) for m in hist_all}
    # Pensionskasse/BVG: ab 2026 strikt quartalsweise (default 3); MWST: Saldosatz
    # -> halbjaehrlich, sonst quartalsweise.
    tax_cadence = 6 if fs.vat_method == "saldo" else 3
    pension_forecast_map = _seasonal_forecast(pension_hist, forecast_months, default_cadence=3)
    tax_forecast_map = _seasonal_forecast(tax_hist, forecast_months, default_cadence=tax_cadence)
    # Sozialversicherungen (monatlich) als Run-Rate; Pensionskasse als 12M-Schnitt
    # nur fuer das repraesentative API-Summenfeld (forecast_expenses_monthly).
    social_12m = [cat_cf.get(m, {}).get("social_outflow", 0) for m in hist_months_12 if m < current_month]
    forecast_social = _trailing_12m_avg(social_12m)
    pension_12m_avg = _trailing_12m_avg([cat_cf.get(m, {}).get("pension_outflow", 0) for m in hist_months_12 if m < current_month])
    tax_12m_avg = _trailing_12m_avg([cat_cf.get(m, {}).get("tax_outflow", 0) for m in hist_months_12 if m < current_month])
    forecast_exp = forecast_personnel + forecast_op + forecast_social + pension_12m_avg + tax_12m_avg + forecast_fin + forecast_inv
    vat_factor = 1 + fs.vat_rate
    cap_monthly = await _compute_capacity_monthly(user, all_month_keys, fs)
    current_idx = all_month_keys.index(current_month) if current_month in all_month_keys else months_back

    rows: list[dict] = []

    for idx, mk in enumerate(all_month_keys):
        is_forecast = mk > current_month
        fc_committed = 0.0
        fc_pipeline = 0.0
        fc_fill = 0.0

        if mk == current_month:
            # Laufender Monat: bereits erfasst (Toggl, netto->brutto) bzw. fakturiert,
            # plus erwarteter Rest aus der gebuchten Kapazitaet des vollen Monats.
            cap = cap_monthly.get(mk, {})
            committed_gross = cap.get("committed_net", 0.0) * vat_factor
            pipeline_gross = cap.get("pipeline_net", 0.0) * vat_factor * fs.pipeline_weight
            booked = committed_gross + pipeline_gross
            actual_gross = current_toggl_revenue * vat_factor if current_toggl_revenue > 0 \
                else revenue_by_month.get(mk, 0)
            rev = max(actual_gross, booked)
            # Chart-Split: erfasst (revActual) + erwarteter Rest (fcFill)
            fc_committed = round(actual_gross, 2)
            fc_fill = round(max(0.0, rev - actual_gross), 2)
            cf_data = cat_cf.get(mk, {})
            actual_personnel = cf_data.get("personnel_outflow", 0)
            actual_op = cf_data.get("op_outflow", 0)
            # Frueh im Monat sind monatlich wiederkehrende Kosten (Lohn, Uebriges)
            # evtl. noch nicht gebucht -> auf Run-Rate hochziehen, damit der
            # laufende Monat nicht kuenstlich tief erscheint. Klumpige Posten
            # (MWST/Sozial) werden NICHT fabriziert -- nur Ist verwenden.
            if today.day <= 15 and (actual_personnel + actual_op) < forecast_monthly_op * 0.5:
                personnel_out = forecast_personnel
                op_exp = forecast_op
            else:
                personnel_out = actual_personnel
                op_exp = actual_op
            social_out = cf_data.get("social_outflow", 0)
            pension_out = cf_data.get("pension_outflow", 0)
            tax_out = cf_data.get("tax_outflow", 0)
            fin_out = cf_data.get("fin_outflow", 0)
            inv_out = cf_data.get("invest_outflow", 0)
            items = [CashflowSpecialItem(**si) for si in cf_data.get("special_items", [])]
            is_fc = False
        elif is_forecast:
            # Gesicherter Umsatz (brutto): gebuchte Kapazitaet + gewichtete Pipeline.
            # Bewusst KEINE Auffuellung auf die Run-Rate -- diese wird separat als
            # Referenzlinie gezeigt. So bleiben Balken, Delta und Saldo konsistent
            # und die Prognose bildet die sinkende Pipeline gegen Jahresende ehrlich ab.
            cap = cap_monthly.get(mk, {})
            committed_gross = cap.get("committed_net", 0.0) * vat_factor
            pipeline_gross = cap.get("pipeline_net", 0.0) * vat_factor * fs.pipeline_weight
            rev = committed_gross + pipeline_gross
            fc_committed = committed_gross
            fc_pipeline = pipeline_gross
            fc_fill = 0.0
            # Monatlich wiederkehrend (Personal, Op, Sozialvers.) als Run-Rate;
            # klumpige Posten (Pensionskasse, MWST/Steuern) saisonal terminiert.
            personnel_out = round(forecast_personnel, 2)
            op_exp = round(forecast_op, 2)
            social_out = round(forecast_social, 2)
            pension_out = round(pension_forecast_map.get(mk, 0.0), 2)
            tax_out = round(tax_forecast_map.get(mk, 0.0), 2)
            fin_out = round(forecast_fin, 2)
            inv_out = round(forecast_inv, 2)
            items = []
            is_fc = True
        else:
            rev = revenue_by_month.get(mk, 0)
            cf_data = cat_cf.get(mk, {})
            personnel_out = cf_data.get("personnel_outflow", 0)
            op_exp = cf_data.get("op_outflow", 0)
            social_out = cf_data.get("social_outflow", 0)
            pension_out = cf_data.get("pension_outflow", 0)
            tax_out = cf_data.get("tax_outflow", 0)
            fin_out = cf_data.get("fin_outflow", 0)
            inv_out = cf_data.get("invest_outflow", 0)
            items = [CashflowSpecialItem(**si) for si in cf_data.get("special_items", [])]
            is_fc = False

        total_out = op_exp + personnel_out + social_out + pension_out + tax_out + fin_out + inv_out
        delta = rev - total_out
        # Erwartetes Szenario: Prognosemonate auf die Run-Rate auffuellen, damit die
        # Saldo-Linie den realistischen Verlauf abbildet (nicht nur gesicherten Umsatz).
        rev_expected = max(rev, forecast_rev) if is_forecast else rev
        delta_expected = rev_expected - total_out
        rows.append({
            "month": mk,
            "revenue": round(rev, 2),
            "expenses": round(op_exp, 2),
            "personnel_outflow": round(personnel_out, 2),
            "social_outflow": round(social_out, 2),
            "pension_outflow": round(pension_out, 2),
            "tax_outflow": round(tax_out, 2),
            "fin_outflow": round(fin_out, 2),
            "invest_outflow": round(inv_out, 2),
            "delta": delta,
            "delta_expected": delta_expected,
            "is_forecast": is_fc,
            "special_items": items,
            "forecast_committed": round(fc_committed, 2),
            "forecast_pipeline": round(fc_pipeline, 2),
            "forecast_fill": round(fc_fill, 2),
        })

    # Kumulierten Saldo am heutigen Banksaldo verankern:
    # laufender Monat == start_balance (realer Saldo heute), Zukunft vorwaerts,
    # Vergangenheit rueckwaerts zurueckgerechnet. So landet die Linie exakt auf
    # dem Ist-Saldo, und der Dezember-Wert entspricht der KPI "Cashflow Ende Jahr".
    anchor_idx = current_idx if 0 <= current_idx < len(rows) else 0
    cumulatives = [0.0] * len(rows)
    cumulatives_expected = [0.0] * len(rows)
    if rows:
        cumulatives[anchor_idx] = start_balance
        cumulatives_expected[anchor_idx] = start_balance
        for i in range(anchor_idx + 1, len(rows)):
            cumulatives[i] = cumulatives[i - 1] + rows[i]["delta"]
            cumulatives_expected[i] = cumulatives_expected[i - 1] + rows[i]["delta_expected"]
        for i in range(anchor_idx - 1, -1, -1):
            cumulatives[i] = cumulatives[i + 1] - rows[i + 1]["delta"]
            cumulatives_expected[i] = cumulatives_expected[i + 1] - rows[i + 1]["delta_expected"]

    months: list[CashflowMonth] = [
        CashflowMonth(
            month=r["month"],
            revenue=r["revenue"],
            expenses=r["expenses"],
            personnel_outflow=r["personnel_outflow"],
            social_outflow=r["social_outflow"],
            pension_outflow=r["pension_outflow"],
            tax_outflow=r["tax_outflow"],
            fin_outflow=r["fin_outflow"],
            invest_outflow=r["invest_outflow"],
            delta=round(r["delta"], 2),
            cumulative=round(cumulatives[i], 2),
            cumulative_expected=round(cumulatives_expected[i], 2),
            is_forecast=r["is_forecast"],
            special_items=r["special_items"],
            forecast_committed=r["forecast_committed"],
            forecast_pipeline=r["forecast_pipeline"],
            forecast_fill=r["forecast_fill"],
        )
        for i, r in enumerate(rows)
    ]

    # Reine Kapazitaets-Prognose (gesamte geplante Kapazitaet, brutto, ungewichtet)
    # als Referenz-Linie -- nutzt dieselben Schichtdaten wie das Layer-Modell.
    capacity_forecast = [
        CapacityForecastMonth(
            month=mk,
            revenue=round((data["committed_net"] + data["pipeline_net"]) * vat_factor, 2),
            hours=round(data["committed_hours"] + data["pipeline_hours"], 2),
        )
        for mk, data in sorted(cap_monthly.items())
        if (data["committed_net"] + data["pipeline_net"]) > 0
    ]

    result = CashflowResponse(
        months=months,
        forecast_revenue_monthly=round(forecast_rev, 2),
        forecast_expenses_monthly=round(forecast_exp, 2),
        start_balance=round(start_balance, 2),
        capacity_forecast=capacity_forecast,
        annual_revenue_goal=round(fs.annual_revenue_goal, 2),
        monthly_revenue_goal=round(fs.annual_revenue_goal / 12.0, 2) if fs.annual_revenue_goal > 0 else 0.0,
        min_liquidity=round(fs.min_liquidity, 2),
    )
    _cashflow_cache[cache_key] = result
    return result


@router.get("/yoy", response_model=YoyResponse)
async def get_year_over_year(user: User = Depends(require_role("owner"))):
    """Vorjahresvergleich: Monatliche Einnahmen/Ausgaben aktuelles vs. Vorjahr."""
    cached = _cashflow_cache.get("yoy")
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    today = date.today()
    cy = today.year
    py = cy - 1

    invoices = await _fetch_recent_invoices(bexio, months=25)
    revenue_by_month = _revenue_by_month_from_invoices(invoices)

    accounts_map = await _get_accounts_map(bexio)
    expenses_by_month = await _compute_expenses_by_month(
        bexio, f"{py}-01-01", today.isoformat(), accounts_map
    )

    month_names = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                   "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

    # Fairer YoY: nur vollständig abgeschlossene Monate vergleichen.
    # Der laufende Monat wird IMMER ausgeschlossen, da er erst am Monatsende
    # vollständig ist (typische Monatsend-Fakturierung verzerrt ihn sonst stark).
    compare_until = today.month - 1

    months: list[YoyMonth] = []
    rev_cy_ytd = 0.0
    rev_py_ytd = 0.0

    for m in range(1, 13):
        mk_current = f"{cy}-{m:02d}"
        mk_prior = f"{py}-{m:02d}"
        rc = revenue_by_month.get(mk_current, 0)
        rp = revenue_by_month.get(mk_prior, 0)
        ec = expenses_by_month.get(mk_current, 0)
        ep = expenses_by_month.get(mk_prior, 0)

        if m <= compare_until:
            rev_cy_ytd += rc
            rev_py_ytd += rp

        months.append(YoyMonth(
            month_label=month_names[m],
            month_num=m,
            revenue_current=round(rc, 2),
            revenue_prior=round(rp, 2),
            expenses_current=round(ec, 2),
            expenses_prior=round(ep, 2),
        ))

    growth_pct = None
    if rev_py_ytd > 0:
        growth_pct = round((rev_cy_ytd - rev_py_ytd) / rev_py_ytd * 100, 1)

    result = YoyResponse(
        current_year=cy,
        prior_year=py,
        months=months,
        revenue_current_ytd=round(rev_cy_ytd, 2),
        revenue_prior_ytd=round(rev_py_ytd, 2),
        growth_pct=growth_pct,
        as_of_date=today.isoformat(),
        compare_until_month=max(compare_until, 0),
        compare_until_label=month_names[compare_until] if 1 <= compare_until <= 12 else "",
    )
    _cashflow_cache["yoy"] = result
    return result


@router.get("/pnl-waterfall", response_model=WaterfallResponse)
async def get_pnl_waterfall(
    period: str = Query(default="ytd", description="'ytd' oder 'YYYY-MM'"),
    user: User = Depends(require_role("owner")),
):
    """P&L-Wasserfall: Umsatz -> Aufwandkategorien -> Ergebnis."""
    cache_key = f"pnl_waterfall:{period}"
    cached = _cashflow_cache.get(cache_key)
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    today = date.today()

    if period == "ytd":
        from_date = f"{today.year}-01-01"
        _wf_month_names = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                           "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
        if today.month >= 2:
            # Nur abgeschlossene Monate: laufender Monat ist wegen Monatsend-
            # Fakturierung unvollständig und würde das Ergebnis verzerren.
            to_date = (today.replace(day=1) - timedelta(days=1)).isoformat()
            period_label = f"YTD per Ende {_wf_month_names[today.month - 1]} {today.year}"
        else:
            # Januar: noch kein abgeschlossener Monat -> laufenden Monat zeigen.
            to_date = today.isoformat()
            period_label = f"YTD {today.year}"
    else:
        y, m = int(period[:4]), int(period[5:7])
        from_date = f"{y}-{m:02d}-01"
        if m == 12:
            to_date = f"{y + 1}-01-01"
        else:
            to_date = f"{y}-{m + 1:02d}-01"
        month_names = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                       "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
        period_label = f"{month_names[m]} {y}"

    invoices = await _fetch_recent_invoices(bexio, months=25)
    revenue_by_month = _revenue_by_month_from_invoices(invoices)
    revenue_total = sum(
        v for mk, v in revenue_by_month.items()
        if from_date[:7] <= mk <= to_date[:7]
    )

    accounts_map = await _get_accounts_map(bexio)
    cat_totals = await _compute_expenses_by_category(
        bexio, from_date, to_date, accounts_map
    )

    steps: list[WaterfallStep] = [
        WaterfallStep(label="Umsatz", value=round(revenue_total, 2), step_type="income")
    ]

    sorted_cats = sorted(
        ((k, v) for k, v in cat_totals.items() if v > 0),
        key=lambda x: x[1],
        reverse=True,
    )

    expenses_total = 0.0
    for cat_key, cat_val in sorted_cats:
        label = EXPENSE_CATEGORIES.get(cat_key, {}).get("label", cat_key.replace("_", " ").title())
        steps.append(WaterfallStep(label=label, value=round(-cat_val, 2), step_type="expense"))
        expenses_total += cat_val

    net_result = revenue_total - expenses_total
    steps.append(WaterfallStep(label="Ergebnis", value=round(net_result, 2), step_type="total"))

    result = WaterfallResponse(
        steps=steps,
        period_label=period_label,
        revenue_total=round(revenue_total, 2),
        expenses_total=round(expenses_total, 2),
        result=round(net_result, 2),
    )
    _cashflow_cache[cache_key] = result
    return result


@router.get("/toggl-summary", response_model=list[TogglProjectSummary])
async def get_toggl_month_summary(
    month: str = Query(default="", description="YYYY-MM, leer = aktueller Monat"),
    user: User = Depends(require_role("owner")),
):
    """Toggl-Stunden pro Projekt fuer einen bestimmten Monat."""
    today = date.today()
    if not month:
        month = _month_key(today)

    cache_key = f"toggl_summary:{month}"
    cached = _overview_cache.get(cache_key)
    if cached is not None:
        return cached

    year, mon = int(month[:4]), int(month[5:7])
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, mon + 1, 1) - timedelta(days=1)
    if end > today:
        end = today

    toggl = _get_toggl_client(user)
    projects = await toggl.list_projects(active="both")
    proj_map = {p.get("id"): p for p in projects}

    clients = await toggl.list_clients()
    client_map = {c.get("id"): c.get("name", "") for c in clients}

    summary_data = await toggl.get_summary_by_project(
        start.isoformat(), end.isoformat(), billable=True
    )

    result: list[TogglProjectSummary] = []
    for group in summary_data:
        pid = group.get("id")
        proj = proj_map.get(pid, {})
        title = group.get("title") or {}
        sub_groups = group.get("sub_groups") or group.get("items") or []

        group_hours = 0.0
        group_amount = 0.0
        group_rate = 0.0
        group_currency = "CHF"

        for item in sub_groups:
            rates = item.get("rates") or []
            for rate_info in rates:
                billable_secs = rate_info.get("billable_seconds", 0) or 0
                hourly_cents = rate_info.get("hourly_rate_in_cents", 0) or 0
                hours = billable_secs / 3600
                group_hours += hours
                group_amount += hours * (hourly_cents / 100)
                if hourly_cents and not group_rate:
                    group_rate = hourly_cents / 100
                if rate_info.get("currency"):
                    group_currency = rate_info["currency"]
            if not rates:
                secs = item.get("seconds", 0) or item.get("time", 0) or 0
                group_hours += secs / 3600

        if group_hours > 0:
            cid = proj.get("client_id")
            result.append(TogglProjectSummary(
                project_name=proj.get("name") or title.get("project") or f"Projekt {pid}",
                client_name=(client_map.get(cid, "") if cid else "") or title.get("client") or "",
                hours=round(group_hours, 2),
                rate_per_hour=round(group_rate, 2),
                amount=round(group_amount, 2),
                currency=group_currency,
            ))

    result.sort(key=lambda x: x.amount, reverse=True)
    _overview_cache[cache_key] = result
    return result


@router.get("/expense-categories", response_model=ExpenseCategoryResponse)
async def get_expense_categories(user: User = Depends(require_role("owner"))):
    """Aufwand-Kategorien mit Durchschnittswerten und tatsaechlichem Zeitraum."""
    cached = _cashflow_cache.get("expense_categories_v2")
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    accounts_map = await _get_accounts_map(bexio)

    today = date.today()
    journal_from = (today.replace(day=1) - timedelta(days=365)).strftime("%Y-%m-%d")
    entries = await _get_journal_data(bexio, journal_from, today.isoformat())

    # Tatsaechlichen Zeitraum aus den Daten ermitteln
    all_expense_dates: list[str] = []
    all_expense_months: set[str] = set()

    cat_totals: dict[str, float] = defaultdict(float)
    cat_months: dict[str, set[str]] = defaultdict(set)

    for e in entries:
        amount = float(e.get("amount", 0))
        entry_date = (e.get("date") or "")[:10]
        entry_month = entry_date[:7]
        did = e.get("debit_account_id")
        cid = e.get("credit_account_id")
        debit_no = accounts_map.get(did, 0)
        credit_no = accounts_map.get(cid, 0)
        if _is_expense_account(debit_no):
            cat_key = _categorize_account(debit_no)
            cat_totals[cat_key] += amount
            if entry_month:
                cat_months[cat_key].add(entry_month)
                all_expense_months.add(entry_month)
                all_expense_dates.append(entry_date)
        if _is_expense_account(credit_no):
            cat_key = _categorize_account(credit_no)
            cat_totals[cat_key] -= amount

    period_from = min(all_expense_dates) if all_expense_dates else journal_from
    period_to = max(all_expense_dates) if all_expense_dates else today.isoformat()
    months_covered = len(all_expense_months)

    categories: list[ExpenseCategory] = []
    for key, cat in EXPENSE_CATEGORIES.items():
        lo, hi = cat["range"]
        total = cat_totals.get(key, 0)
        months_active = len(cat_months.get(key, set()))
        avg = total / months_covered if months_covered else 0

        recurrence = "unbekannt"
        if months_active >= 10:
            recurrence = "monatlich"
        elif 2 <= months_active <= 4:
            recurrence = "quartalsweise"
        elif months_active == 1:
            recurrence = "jaehrlich"

        categories.append(ExpenseCategory(
            key=key,
            label=cat["label"],
            account_range=f"{lo}-{hi}",
            monthly_average=round(avg, 2),
            total_12m=round(total, 2),
            recurrence=recurrence,
        ))

    categories.sort(key=lambda c: c.total_12m, reverse=True)
    result = ExpenseCategoryResponse(
        categories=categories,
        period_from=period_from[:7],
        period_to=period_to[:7],
        months_covered=months_covered,
    )
    _cashflow_cache["expense_categories_v2"] = result
    return result


# ── Monatliche Kostenstruktur (Stacked Bar) ───────────────

class ExpenseMonthRow(BaseModel):
    month: str
    year: int
    categories: dict[str, float]
    total: float = 0


class ExpenseMonthlyBreakdownResponse(BaseModel):
    current_year: int
    prior_year: int
    months_current: list[ExpenseMonthRow]
    months_prior: list[ExpenseMonthRow]
    category_labels: dict[str, str]


@router.get("/expense-monthly-breakdown", response_model=ExpenseMonthlyBreakdownResponse)
async def get_expense_monthly_breakdown(user: User = Depends(require_role("owner"))):
    """Monatliche Kostenverteilung nach KMU-Kategorie, aktuelles Jahr vs. Vorjahr."""
    cached = _cashflow_cache.get("expense_monthly_breakdown")
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    accounts_map = await _get_accounts_map(bexio)
    today = date.today()
    cy = today.year
    py = cy - 1

    entries = await _get_journal_data(bexio, f"{py}-01-01", today.isoformat())

    monthly_cats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for e in entries:
        entry_date = (e.get("date") or "")[:10]
        if len(entry_date) < 7:
            continue
        mk = entry_date[:7]
        amount = float(e.get("amount", 0))
        did = e.get("debit_account_id")
        cid = e.get("credit_account_id")
        debit_no = accounts_map.get(did, 0)
        credit_no = accounts_map.get(cid, 0)
        if _is_expense_account(debit_no):
            cat = _categorize_account(debit_no)
            monthly_cats[mk][cat] += amount
        if _is_expense_account(credit_no):
            cat = _categorize_account(credit_no)
            monthly_cats[mk][cat] -= amount

    month_names = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                   "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

    def _build_rows(year: int) -> list[ExpenseMonthRow]:
        rows = []
        for m in range(1, 13):
            mk = f"{year}-{m:02d}"
            cats = dict(monthly_cats.get(mk, {}))
            cats = {k: round(v, 2) for k, v in cats.items() if v > 0}
            rows.append(ExpenseMonthRow(
                month=month_names[m],
                year=year,
                categories=cats,
                total=round(sum(cats.values()), 2),
            ))
        return rows

    cat_labels = {k: v["label"] for k, v in EXPENSE_CATEGORIES.items()}
    cat_labels["materialaufwand"] = "Materialaufwand"
    cat_labels["uebr_personal"] = "Übriger Personalaufwand"
    cat_labels["sonstige"] = "Sonstige"

    result = ExpenseMonthlyBreakdownResponse(
        current_year=cy,
        prior_year=py,
        months_current=_build_rows(cy),
        months_prior=_build_rows(py),
        category_labels=cat_labels,
    )
    _cashflow_cache["expense_monthly_breakdown"] = result
    return result


# ── Marge-Trend (YTD-kumuliert + 12-Mt-Rolling) ──────────

class MarginMonth(BaseModel):
    month: str
    label: str
    ytd_margin: float | None = None
    rolling_12m_margin: float | None = None
    ytd_margin_prior: float | None = None


class MarginTrendResponse(BaseModel):
    months: list[MarginMonth]
    current_year: int
    prior_year: int


@router.get("/margin-trend", response_model=MarginTrendResponse)
async def get_margin_trend(user: User = Depends(require_role("owner"))):
    """Gewinnmarge: YTD-kumuliert + 12-Mt-Rolling + Vorjahr als Benchmark."""
    cached = _cashflow_cache.get("margin_trend")
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    today = date.today()
    cy = today.year
    py = cy - 1

    invoices = await _fetch_recent_invoices(bexio, months=30)
    rev_by_month = _revenue_by_month_from_invoices(invoices)

    accounts_map = await _get_accounts_map(bexio)
    exp_by_month = await _compute_expenses_by_month(
        bexio, f"{py - 1}-01-01", today.isoformat(), accounts_map
    )

    mwst_satz = get_forecast_settings_from_settings(user.settings).vat_rate
    month_names = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                   "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

    def _ytd_margin(year: int, up_to_month: int) -> float | None:
        rev_sum = sum(rev_by_month.get(f"{year}-{m:02d}", 0) for m in range(1, up_to_month + 1))
        exp_sum = sum(exp_by_month.get(f"{year}-{m:02d}", 0) for m in range(1, up_to_month + 1))
        rev_net = rev_sum / (1 + mwst_satz)
        if rev_net <= 0:
            return None
        return round((rev_net - exp_sum) / rev_net * 100, 1)

    def _rolling_12m_margin(year: int, month: int) -> float | None:
        months_back = []
        for offset in range(12):
            m = month - offset
            y = year
            while m < 1:
                m += 12
                y -= 1
            months_back.append(f"{y}-{m:02d}")
        rev_sum = sum(rev_by_month.get(mk, 0) for mk in months_back)
        exp_sum = sum(exp_by_month.get(mk, 0) for mk in months_back)
        rev_net = rev_sum / (1 + mwst_satz)
        if rev_net <= 0:
            return None
        return round((rev_net - exp_sum) / rev_net * 100, 1)

    compare_until = today.month if today.day >= 15 else today.month - 1

    months: list[MarginMonth] = []
    for m in range(1, 13):
        if m > compare_until:
            break
        mk = f"{cy}-{m:02d}"
        months.append(MarginMonth(
            month=mk,
            label=f"{month_names[m]} {str(cy)[2:]}",
            ytd_margin=_ytd_margin(cy, m),
            rolling_12m_margin=_rolling_12m_margin(cy, m),
            ytd_margin_prior=_ytd_margin(py, m),
        ))

    result = MarginTrendResponse(months=months, current_year=cy, prior_year=py)
    _cashflow_cache["margin_trend"] = result
    return result


# ── Kreuz-Validierung ────────────────────────────────────

@router.get("/validate/2025")
async def validate_2025(user: User = Depends(require_role("owner"))):
    """Vergleiche Dashboard-Werte mit Jahresrechnung 2025."""
    bexio = _get_bexio_client(user)
    accounts_map = await _get_accounts_map(bexio)

    cat_totals = await _compute_expenses_by_category(
        bexio, "2025-01-01", "2025-12-31", accounts_map
    )

    invoices = await _fetch_recent_invoices(bexio, months=25)
    rev = _revenue_by_month_from_invoices(invoices)
    revenue_2025 = sum(v for mk, v in rev.items() if mk.startswith("2025"))

    expenses_by_month = await _compute_expenses_by_month(
        bexio, "2025-01-01", "2025-12-31", accounts_map
    )
    total_expenses = sum(expenses_by_month.values())

    jr = {
        "total_ertrag_brutto": 396_485.84,
        "mwst_saldosteuer": 23_670.93,
        "total_ertrag_netto": 372_114.91,
        "personalaufwand": 296_746.17,
        "uebr_betriebsaufwand": 29_674.44,
        "abschreibungen": 1_398.40,
        "finanzaufwand": 102.95,
        "steuern": 3_588.40,
        "jahresgewinn": 39_804.21,
    }

    return {
        "dashboard_revenue_brutto_2025": round(revenue_2025, 2),
        "dashboard_expenses_total_2025": round(total_expenses, 2),
        "dashboard_categories_2025": {k: round(v, 2) for k, v in sorted(cat_totals.items())},
        "jahresrechnung_referenz": jr,
        "differenz_umsatz_brutto": round(revenue_2025 - jr["total_ertrag_brutto"], 2),
        "differenz_aufwand": round(total_expenses - (jr["personalaufwand"] + jr["uebr_betriebsaufwand"] + jr["abschreibungen"] + jr["finanzaufwand"] + jr["steuern"]), 2),
    }


# ── Saldenbilanz + Bilanzkennzahlen ──────────────────────

@router.get("/balance-sheet", response_model=BalanceSheetResponse)
async def get_balance_sheet(user: User = Depends(require_role("owner"))):
    """Saldenbilanz + Bilanzkennzahlen (EK-Quote, Liquiditaetsgrade, Working Capital).

    Aus den Journal-Buchungen ab Geschaeftsjahr-Beginn abgeleitet (inkl.
    Eroeffnungsbuchungen). Das laufende Jahresergebnis wird dem Eigenkapital
    zugeschlagen, damit die Bilanz aufgeht.
    """
    cached = _cashflow_cache.get("balance_sheet")
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    accounts_map = await _get_accounts_map(bexio)
    bs = await _compute_balance_sheet(bexio, accounts_map)

    fy_start = await _get_fy_start(bexio)
    result = BalanceSheetResponse(
        **bs,
        period_from=fy_start,
        period_to=date.today().isoformat(),
    )
    _cashflow_cache["balance_sheet"] = result
    return result


# ── Kosten pro Konto (granular) ──────────────────────────

@router.get("/expenses-by-account", response_model=ExpensesByAccountResponse)
async def get_expenses_by_account(
    months: int = Query(12, ge=1, le=36, description="Anzahl Monate rueckblickend"),
    user: User = Depends(require_role("owner")),
):
    """Aufwand je Einzelkonto (Kontonummer + Bezeichnung) mit Monatsverlauf.

    Feinere Granularitaet als die KMU-Kategorien: Basis fuer Kostenanalysen.
    """
    cache_key = f"expenses_by_account:{months}"
    cached = _cashflow_cache.get(cache_key)
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    accounts_meta = await _get_accounts_meta(bexio)

    today = date.today()
    from_date = (today.replace(day=1) - timedelta(days=30 * months)).strftime("%Y-%m-%d")
    to_date = today.isoformat()
    current_year = str(today.year)

    per_acc = await _compute_expenses_by_account(bexio, from_date, to_date, accounts_meta)

    # Tatsaechlich abgedeckte Monate (fuer 12M-Durchschnitt)
    all_months: set[str] = set()
    for bucket in per_acc.values():
        all_months.update(bucket["monthly"].keys())
    months_covered = len(all_months) or 1

    items: list[ExpenseAccountItem] = []
    grand_total = 0.0
    grand_total_ytd = 0.0
    for bucket in per_acc.values():
        monthly = {mk: round(v, 2) for mk, v in sorted(bucket["monthly"].items())}
        total = round(bucket["total"], 2)
        total_ytd = round(
            sum(v for mk, v in bucket["monthly"].items() if mk.startswith(current_year)),
            2,
        )
        if abs(total) < 0.005 and abs(total_ytd) < 0.005:
            continue
        cat_key = bucket["category"]
        cat_label = EXPENSE_CATEGORIES.get(cat_key, {}).get("label", cat_key)
        items.append(ExpenseAccountItem(
            account_no=bucket["account_no"],
            name=bucket["name"],
            category=cat_key,
            category_label=cat_label,
            total=total,
            total_ytd=total_ytd,
            monthly_avg_12m=round(total / months_covered, 2),
            monthly=monthly,
        ))
        grand_total += total
        grand_total_ytd += total_ytd

    items.sort(key=lambda x: x.total, reverse=True)
    result = ExpensesByAccountResponse(
        accounts=items,
        total=round(grand_total, 2),
        total_ytd=round(grand_total_ytd, 2),
        period_from=from_date[:7],
        period_to=to_date[:7],
        months_covered=months_covered,
    )
    _cashflow_cache[cache_key] = result
    return result


# ── Cache-Verwaltung ─────────────────────────────────────

@router.post("/cache/clear")
async def clear_cache(user: User = Depends(require_role("owner"))):
    _overview_cache.clear()
    _cashflow_cache.clear()
    _journal_cache.clear()
    _accounts_cache.clear()
    logger.info("Finance-Caches manuell geleert")
    return {"status": "ok", "message": "Alle Finance-Caches geleert"}


@router.get("/cache/stats")
async def cache_stats(user: User = Depends(require_role("owner"))):
    return {
        "overview_cache": {"size": len(_overview_cache), "maxsize": _overview_cache.maxsize, "ttl": _overview_cache.ttl},
        "cashflow_cache": {"size": len(_cashflow_cache), "maxsize": _cashflow_cache.maxsize, "ttl": _cashflow_cache.ttl},
        "journal_cache": {"size": len(_journal_cache), "maxsize": _journal_cache.maxsize, "ttl": _journal_cache.ttl},
        "accounts_cache": {"size": len(_accounts_cache), "maxsize": _accounts_cache.maxsize, "ttl": _accounts_cache.ttl},
    }
