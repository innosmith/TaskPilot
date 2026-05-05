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

from app.auth.deps import get_current_user
from app.models import User

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


async def _compute_bank_balance(
    bexio: BexioClient,
    bank_account_ids: set[int],
) -> float:
    """Banksaldo: Summe aller Buchungen auf Bankkonten seit Geschaeftsjahr-Beginn."""
    fy_start = "2025-01-01"
    try:
        years = await bexio.get_business_years()
        open_years = [y for y in years if y.get("status") == "open"]
        if open_years:
            fy_start = open_years[0].get("start", fy_start)
    except Exception:
        pass

    entries = await _get_journal_data(bexio, fy_start, date.today().isoformat())
    debit_sum = sum(
        float(e.get("amount", 0))
        for e in entries
        if e.get("debit_account_id") in bank_account_ids
    )
    credit_sum = sum(
        float(e.get("amount", 0))
        for e in entries
        if e.get("credit_account_id") in bank_account_ids
    )
    return debit_sum - credit_sum


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
    2201: "MWST-Zahlung",
    2300: "Passive RA",
    2302: "Ferienguthaben",
    2970: "Gewinnvortrag",
    2950: "Gesetzl. Reserve",
}


async def _compute_categorized_cashflow(
    bexio: BexioClient,
    bank_account_ids: set[int],
    from_date: str,
    to_date: str,
    accounts_map: dict[int, int],
) -> dict[str, dict]:
    """Kategorisierter Cashflow pro Monat aus Bankkonten (direkte Methode).

    Jede Bankbuchung wird anhand des Gegenkontos klassifiziert:
    - operativ (Aufwand/Ertrag 3xxx-8xxx)
    - investiv (Anlagen 1500-1599)
    - Finanzierung (Eigenkapital/FK 2xxx)
    """
    entries = await _get_journal_data(bexio, from_date, to_date)
    flows: dict[str, dict] = defaultdict(lambda: {
        "inflow": 0.0, "op_outflow": 0.0,
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
            if 1500 <= gegen_no <= 1599:
                flows[mk]["invest_outflow"] += amount
            elif 2000 <= gegen_no <= 2999:
                flows[mk]["fin_outflow"] += amount
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
    forecast_year_end_cashflow: float = 0
    burn_rate: float = 0
    runway_months: float | None = None
    runway_months_incl_debtors: float | None = None
    profit_margin_ytd: float | None = None
    revenue_ytd: float = 0
    revenue_ytd_net: float = 0
    expenses_ytd: float = 0
    ebitda_ytd: float | None = None
    personalquote_ytd: float | None = None
    dso_days: float | None = None
    liquiditaet_2: float | None = None
    ek_quote: float | None = None
    revenue_ytd_prior: float = 0
    expenses_ytd_prior: float = 0
    ebitda_ytd_prior: float | None = None
    personalquote_ytd_prior: float | None = None
    profit_margin_ytd_prior: float | None = None
    journal_data_from: str | None = None
    journal_data_to: str | None = None
    currency: str = "CHF"


class CashflowMonth(BaseModel):
    month: str
    revenue: float = 0
    expenses: float = 0
    fin_outflow: float = 0
    invest_outflow: float = 0
    delta: float = 0
    cumulative: float = 0
    is_forecast: bool = False
    special_items: list[CashflowSpecialItem] = []


class CashflowResponse(BaseModel):
    months: list[CashflowMonth]
    forecast_revenue_monthly: float = 0
    forecast_expenses_monthly: float = 0
    start_balance: float = 0


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


# ── Endpoints ────────────────────────────────────────────

@router.get("/overview", response_model=KpiOverview)
async def get_overview(user: User = Depends(get_current_user)):
    """KPI-Uebersicht mit Jahresprognosen, Burn Rate und Runway."""
    cached = _overview_cache.get("overview")
    if cached is not None:
        return cached

    bexio = _get_bexio_client(user)
    today = date.today()
    current_year = today.year
    current_month = _month_key(today)

    # Banksaldo via Journal
    bank_balance = None
    bank_name = None
    try:
        bank_accounts = await bexio.list_bank_accounts()
        if bank_accounts:
            bank_name = bank_accounts[0].get("name", "Hauptkonto")
            bank_ids = {a.get("account_id") for a in bank_accounts if a.get("account_id")}
            if bank_ids:
                bank_balance = await _compute_bank_balance(bexio, bank_ids)
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

    # YTD Revenue
    revenue_ytd = sum(
        v for mk, v in revenue_by_month.items()
        if mk.startswith(str(current_year)) and mk <= current_month
    )

    # Ausgaben
    accounts_map: dict[int, int] = {}
    expenses_by_month: dict[str, float] = {}
    try:
        accounts_map = await _get_accounts_map(bexio)
        journal_from = f"{current_year - 1}-01-01"
        expenses_by_month = await _compute_expenses_by_month(
            bexio, journal_from, today.isoformat(), accounts_map
        )
    except Exception as e:
        logger.warning("Ausgaben nicht verfuegbar: %s", e)

    # Prognose-Basis (letzte 3 und 12 Monate) -- nur abgeschlossene Monate
    hist_months_12 = _month_range(12, 0)[:-1]
    hist_months_3 = hist_months_12[-3:] if len(hist_months_12) >= 3 else hist_months_12
    rev_3m = [revenue_by_month.get(m, 0) for m in hist_months_3 if m < current_month]
    rev_12m = [revenue_by_month.get(m, 0) for m in hist_months_12 if m < current_month]
    exp_3m = [expenses_by_month.get(m, 0) for m in hist_months_3 if m < current_month]
    exp_12m = [expenses_by_month.get(m, 0) for m in hist_months_12 if m < current_month]

    forecast_rev = _weighted_forecast(rev_3m, rev_12m)
    forecast_exp = _weighted_forecast(exp_3m, exp_12m)

    # Fix 1: Laufender Monat -- Prognose-Ausgaben wenn Journal noch leer
    actual_current_exp = expenses_by_month.get(current_month, 0)
    if today.day <= 15 and actual_current_exp < forecast_exp * 0.5:
        current_month_exp = forecast_exp
    else:
        current_month_exp = actual_current_exp

    # YTD Expenses (abgeschlossene Monate + korrigierter laufender Monat)
    expenses_ytd = sum(
        v for mk, v in expenses_by_month.items()
        if mk.startswith(str(current_year)) and mk < current_month
    ) + current_month_exp

    # Burn Rate = durchschnittliche monatliche Ausgaben
    burn_rate = forecast_exp

    # Runway
    runway_months = None
    runway_months_incl_debtors = None
    if bank_balance is not None and burn_rate > 0:
        runway_months = round(bank_balance / burn_rate, 1)
        runway_months_incl_debtors = round((bank_balance + open_total) / burn_rate, 1)

    # Jahresprognose
    months_elapsed = today.month
    months_remaining = 12 - months_elapsed
    forecast_year_revenue = revenue_ytd + months_remaining * forecast_rev
    forecast_year_end_cashflow = (bank_balance or 0) + months_remaining * (forecast_rev - forecast_exp)

    # Netto-Umsatz (MWST-Saldosteuersatz 8.1% abziehen -- CH-Standard fuer Dienstleister)
    mwst_satz = 0.081
    revenue_ytd_net = round(revenue_ytd / (1 + mwst_satz), 2)

    # Gewinnmarge YTD (auf Nettoumsatz)
    profit_margin_ytd = None
    if revenue_ytd_net > 0:
        profit_margin_ytd = round((revenue_ytd_net - expenses_ytd) / revenue_ytd_net * 100, 1)

    # EBITDA YTD: Netto-Ertrag - Aufwand ohne Abschreibungen, Finanz, Steuern
    ebitda_ytd = None
    try:
        cat_ytd = await _compute_expenses_by_category(
            bexio, f"{current_year}-01-01", today.isoformat(), accounts_map
        )
        non_ebitda_cats = {"abschreibungen", "finanzaufwand", "steuern", "ausserordentlich"}
        operating_exp = sum(v for k, v in cat_ytd.items() if k not in non_ebitda_cats)
        ebitda_ytd = round(revenue_ytd_net - operating_exp, 2)
    except Exception:
        pass

    # Personalquote YTD: Personalaufwand / Netto-Ertrag
    personalquote_ytd = None
    try:
        personal_cats = {"loehne", "sozialversicherungen", "pensionskasse", "uvg_ktg",
                         "spesen_personal", "personalaufwand_sonstig", "uebr_personal"}
        personal_total = sum(v for k, v in cat_ytd.items() if k in personal_cats)
        if revenue_ytd_net > 0:
            personalquote_ytd = round(personal_total / revenue_ytd_net * 100, 1)
    except Exception:
        pass

    # DSO (Days Sales Outstanding): Offene Debitoren / Tagesumsatz
    dso_days = None
    if revenue_ytd > 0 and months_elapsed > 0:
        daily_rev = revenue_ytd / (months_elapsed * 30)
        if daily_rev > 0:
            dso_days = round(open_total / daily_rev, 0)

    # Liquiditaetsgrad 2: (Fluessige Mittel + Debitoren) / kurzfristiges FK
    liquiditaet_2 = None
    ek_quote = None

    # ── Vorjahres-KPIs (YTD bis gleicher Tag im Vorjahr) ──
    prior_year = current_year - 1
    prior_date = f"{prior_year}-{today.month:02d}-{today.day:02d}"
    prior_month_key = f"{prior_year}-{today.month:02d}"

    revenue_ytd_prior = sum(
        v for mk, v in revenue_by_month.items()
        if mk.startswith(str(prior_year)) and mk <= prior_month_key
    )

    expenses_ytd_prior = 0.0
    try:
        prior_expenses = await _compute_expenses_by_month(
            bexio, f"{prior_year}-01-01", prior_date, accounts_map
        )
        expenses_ytd_prior = sum(prior_expenses.values())
    except Exception:
        pass

    revenue_ytd_net_prior = round(revenue_ytd_prior / (1 + mwst_satz), 2)
    profit_margin_ytd_prior = None
    if revenue_ytd_net_prior > 0:
        profit_margin_ytd_prior = round(
            (revenue_ytd_net_prior - expenses_ytd_prior) / revenue_ytd_net_prior * 100, 1
        )

    ebitda_ytd_prior = None
    personalquote_ytd_prior = None
    try:
        cat_prior = await _compute_expenses_by_category(
            bexio, f"{prior_year}-01-01", prior_date, accounts_map
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

    # Toggl: laufender Monat
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

    result = KpiOverview(
        bank_balance=round(bank_balance, 2) if bank_balance is not None else None,
        bank_account_name=bank_name,
        open_invoices_total=round(open_total, 2),
        open_invoices_count=open_count,
        current_month_revenue=round(current_revenue, 2),
        current_month_hours=round(current_hours, 2),
        forecast_year_revenue=round(forecast_year_revenue, 2),
        forecast_year_end_cashflow=round(forecast_year_end_cashflow, 2),
        burn_rate=round(burn_rate, 2),
        runway_months=runway_months,
        runway_months_incl_debtors=runway_months_incl_debtors,
        profit_margin_ytd=profit_margin_ytd,
        revenue_ytd=round(revenue_ytd, 2),
        revenue_ytd_net=revenue_ytd_net,
        expenses_ytd=round(expenses_ytd, 2),
        ebitda_ytd=ebitda_ytd,
        personalquote_ytd=personalquote_ytd,
        dso_days=dso_days,
        liquiditaet_2=liquiditaet_2,
        ek_quote=ek_quote,
        revenue_ytd_prior=round(revenue_ytd_prior, 2),
        expenses_ytd_prior=round(expenses_ytd_prior, 2),
        ebitda_ytd_prior=ebitda_ytd_prior,
        personalquote_ytd_prior=personalquote_ytd_prior,
        profit_margin_ytd_prior=profit_margin_ytd_prior,
        journal_data_from=journal_from_str,
        journal_data_to=journal_to_str,
    )
    _overview_cache["overview"] = result
    return result


@router.get("/cashflow", response_model=CashflowResponse)
async def get_cashflow(
    months_back: int = Query(default=6, ge=1, le=24),
    months_forward: int = Query(default=12, ge=1, le=24),
    user: User = Depends(get_current_user),
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

    # Operative Abfluesse fuer Prognose (ohne Finanz/Investiv)
    op_exp_3m = [cat_cf.get(m, {}).get("op_outflow", 0) for m in hist_months_3 if m < current_month]
    op_exp_12m = [cat_cf.get(m, {}).get("op_outflow", 0) for m in hist_months_12 if m < current_month]

    # Finanzierungs- und Investitionsabfluesse fuer Prognose
    fin_3m = [cat_cf.get(m, {}).get("fin_outflow", 0) for m in hist_months_3 if m < current_month]
    fin_12m = [cat_cf.get(m, {}).get("fin_outflow", 0) for m in hist_months_12 if m < current_month]
    inv_3m = [cat_cf.get(m, {}).get("invest_outflow", 0) for m in hist_months_3 if m < current_month]
    inv_12m = [cat_cf.get(m, {}).get("invest_outflow", 0) for m in hist_months_12 if m < current_month]

    forecast_rev = _weighted_forecast(rev_3m, rev_12m)
    forecast_exp = _weighted_forecast(op_exp_3m, op_exp_12m)
    forecast_fin = _weighted_forecast(fin_3m, fin_12m)
    forecast_inv = _weighted_forecast(inv_3m, inv_12m)

    months: list[CashflowMonth] = []
    cumulative = start_balance

    for mk in all_month_keys:
        is_forecast = mk > current_month

        if mk == current_month:
            rev = current_toggl_revenue if current_toggl_revenue > 0 else revenue_by_month.get(mk, 0)
            cf_data = cat_cf.get(mk, {})
            actual_op = cf_data.get("op_outflow", 0)
            if today.day <= 15 and actual_op < forecast_exp * 0.5:
                op_exp = forecast_exp
            else:
                op_exp = actual_op
            fin_out = cf_data.get("fin_outflow", 0)
            inv_out = cf_data.get("invest_outflow", 0)
            items = [CashflowSpecialItem(**si) for si in cf_data.get("special_items", [])]
            is_fc = False
        elif is_forecast:
            rev = forecast_rev
            op_exp = forecast_exp
            fin_out = round(forecast_fin, 2)
            inv_out = round(forecast_inv, 2)
            items = []
            is_fc = True
        else:
            rev = revenue_by_month.get(mk, 0)
            cf_data = cat_cf.get(mk, {})
            op_exp = cf_data.get("op_outflow", 0)
            fin_out = cf_data.get("fin_outflow", 0)
            inv_out = cf_data.get("invest_outflow", 0)
            items = [CashflowSpecialItem(**si) for si in cf_data.get("special_items", [])]
            is_fc = False

        total_out = op_exp + fin_out + inv_out
        delta = rev - total_out
        cumulative += delta
        months.append(CashflowMonth(
            month=mk,
            revenue=round(rev, 2),
            expenses=round(op_exp, 2),
            fin_outflow=round(fin_out, 2),
            invest_outflow=round(inv_out, 2),
            delta=round(delta, 2),
            cumulative=round(cumulative, 2),
            is_forecast=is_fc,
            special_items=items,
        ))

    result = CashflowResponse(
        months=months,
        forecast_revenue_monthly=round(forecast_rev, 2),
        forecast_expenses_monthly=round(forecast_exp, 2),
        start_balance=round(start_balance, 2),
    )
    _cashflow_cache[cache_key] = result
    return result


@router.get("/yoy", response_model=YoyResponse)
async def get_year_over_year(user: User = Depends(get_current_user)):
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

    # Unvollstaendigen Monat aus YTD ausschliessen
    compare_until = today.month if today.day >= 15 else today.month - 1

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
    )
    _cashflow_cache["yoy"] = result
    return result


@router.get("/pnl-waterfall", response_model=WaterfallResponse)
async def get_pnl_waterfall(
    period: str = Query(default="ytd", description="'ytd' oder 'YYYY-MM'"),
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    projects = await toggl.list_projects(active=None)
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
                project_name=proj.get("name") or f"Projekt {pid}",
                client_name=client_map.get(cid, "") if cid else "",
                hours=round(group_hours, 2),
                rate_per_hour=round(group_rate, 2),
                amount=round(group_amount, 2),
                currency=group_currency,
            ))

    result.sort(key=lambda x: x.amount, reverse=True)
    _overview_cache[cache_key] = result
    return result


@router.get("/expense-categories", response_model=ExpenseCategoryResponse)
async def get_expense_categories(user: User = Depends(get_current_user)):
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
async def get_expense_monthly_breakdown(user: User = Depends(get_current_user)):
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
async def get_margin_trend(user: User = Depends(get_current_user)):
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

    mwst_satz = 0.081
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
async def validate_2025(user: User = Depends(get_current_user)):
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


# ── Cache-Verwaltung ─────────────────────────────────────

@router.post("/cache/clear")
async def clear_cache(user: User = Depends(get_current_user)):
    _overview_cache.clear()
    _cashflow_cache.clear()
    _journal_cache.clear()
    _accounts_cache.clear()
    logger.info("Finance-Caches manuell geleert")
    return {"status": "ok", "message": "Alle Finance-Caches geleert"}


@router.get("/cache/stats")
async def cache_stats(user: User = Depends(get_current_user)):
    return {
        "overview_cache": {"size": len(_overview_cache), "maxsize": _overview_cache.maxsize, "ttl": _overview_cache.ttl},
        "cashflow_cache": {"size": len(_cashflow_cache), "maxsize": _cashflow_cache.maxsize, "ttl": _cashflow_cache.ttl},
        "journal_cache": {"size": len(_journal_cache), "maxsize": _journal_cache.maxsize, "ttl": _journal_cache.ttl},
        "accounts_cache": {"size": len(_accounts_cache), "maxsize": _accounts_cache.maxsize, "ttl": _accounts_cache.ttl},
    }
