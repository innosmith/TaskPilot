"""Debitorensicht -- Kundenzentrisches Finanz-Cockpit.

Aggregiert Daten aus Bexio (Rechnungen, Kontakte) und Toggl Track
(Stundenerfassung pro Projekt/Kunde) zu einer Debitorenübersicht.
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

logger = logging.getLogger("taskpilot.debtors")

router = APIRouter(prefix="/api/debtors", tags=["debtors"])

_cache: TTLCache = TTLCache(maxsize=10, ttl=300)


# ── Client-Helfer (identisch mit finance.py) ─────────────

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


# ── Bexio-Helfer ─────────────────────────────────────────

def _parse_invoice_total(inv: dict) -> float:
    for field in ("total", "total_gross"):
        val = inv.get(field)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return 0.0


def _invoice_is_open(inv: dict) -> bool:
    remaining = inv.get("total_remaining_payments")
    if remaining is not None:
        try:
            return float(remaining) > 0.01
        except (ValueError, TypeError):
            pass
    return inv.get("kb_item_status_id") in (7, 8, 9)


def _open_amount(inv: dict) -> float:
    remaining = inv.get("total_remaining_payments")
    if remaining is not None:
        try:
            return float(remaining)
        except (ValueError, TypeError):
            pass
    return _parse_invoice_total(inv)


async def _fetch_invoices(bexio: BexioClient, months: int = 25) -> list[dict]:
    from_date = (date.today().replace(day=1) - timedelta(days=30 * months)).strftime("%Y-%m-%d")
    try:
        results = await bexio.search_invoices(from_date=from_date)
        if results:
            return results
    except Exception as e:
        logger.warning("Bexio Rechnungssuche fehlgeschlagen: %s -- Fallback", e)
    return await bexio.list_invoices(limit=500)


# ── Response-Modelle ─────────────────────────────────────

class TogglProjectRow(BaseModel):
    project_id: int = 0
    project_name: str
    client_id: int | None = None
    client_name: str = ""
    hours: float = 0
    billable_hours: float = 0
    is_billable: bool = True
    pct_of_total: float = 0
    rate_per_hour: float = 0
    amount: float = 0
    budget_hours: float | None = None
    budget_pct: float | None = None


class TogglMonthSummary(BaseModel):
    total_hours: float = 0
    billable_hours: float = 0
    non_billable_hours: float = 0
    billable_ratio: float = 0
    total_amount: float = 0
    avg_daily_hours: float = 0
    forecast_month_amount: float = 0
    working_days_total: int = 0
    working_days_elapsed: int = 0
    projects: list[TogglProjectRow] = []


class DebtorSummary(BaseModel):
    contact_id: int
    contact_name: str
    revenue_ytd: float = 0
    revenue_prior_year: float = 0
    revenue_delta_pct: float | None = None
    open_invoices_count: int = 0
    open_invoices_total: float = 0
    avg_payment_days: float | None = None
    aging_0_30: float = 0
    aging_31_60: float = 0
    aging_61_90: float = 0
    aging_over_90: float = 0
    project_count: int = 0


class RevenueByMonth(BaseModel):
    contact_id: int
    contact_name: str
    months: dict[str, float] = {}


class DebtorsResponse(BaseModel):
    toggl_month: TogglMonthSummary
    debtors: list[DebtorSummary]
    revenue_trend: list[RevenueByMonth] = []
    total_open: float = 0
    total_revenue_ytd: float = 0
    dso_days: float | None = None
    currency: str = "CHF"


# ── Arbeitstage-Berechnung ───────────────────────────────

def _working_days_in_month(year: int, month: int) -> int:
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    count = 0
    d = first
    while d <= last:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def _working_days_elapsed(year: int, month: int) -> int:
    first = date(year, month, 1)
    today = date.today()
    end = min(today, date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1))
    count = 0
    d = first
    while d <= end:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


# ── Haupt-Endpoint ───────────────────────────────────────

@router.get("", response_model=DebtorsResponse)
async def get_debtors(
    user: User = Depends(get_current_user),
):
    """Debitorenübersicht: Toggl-Monats-Cockpit + Bexio-Debitoren."""
    cached = _cache.get("debtors")
    if cached is not None:
        return cached

    today = date.today()
    current_year = today.year
    prior_year = current_year - 1

    # ── Toggl: Monats-Cockpit ────────────────────────────
    toggl_month = TogglMonthSummary()
    try:
        toggl = _get_toggl_client(user)
        month_start = today.replace(day=1).isoformat()
        month_end = today.isoformat()

        projects_all = await toggl.list_projects(active=None)
        proj_map = {p.get("id"): p for p in projects_all}

        clients = await toggl.list_clients()
        client_map = {c.get("id"): c.get("name", "") for c in clients}

        # Alle Stunden (billable + non-billable)
        all_summary = await toggl.get_summary_by_project(
            month_start, month_end, billable=None,
        )
        # Nur billable
        billable_summary = await toggl.get_summary_by_project(
            month_start, month_end, billable=True,
        )

        # Billable-Stunden pro Projekt sammeln
        billable_by_pid: dict[int, tuple[float, float, float]] = {}
        for group in billable_summary:
            pid = group.get("id", 0)
            sub_groups = group.get("sub_groups") or group.get("items") or []
            b_hours = 0.0
            b_amount = 0.0
            b_rate = 0.0
            for item in sub_groups:
                rates = item.get("rates") or []
                for rate_info in rates:
                    secs = rate_info.get("billable_seconds", 0) or 0
                    cents = rate_info.get("hourly_rate_in_cents", 0) or 0
                    h = secs / 3600
                    b_hours += h
                    b_amount += h * (cents / 100)
                    if cents and not b_rate:
                        b_rate = cents / 100
                if not rates:
                    secs = item.get("seconds", 0) or item.get("time", 0) or 0
                    b_hours += secs / 3600
            billable_by_pid[pid] = (b_hours, b_amount, b_rate)

        # Budgets aus Settings
        budgets: dict[str, dict] = (user.settings or {}).get("debtor_budgets") or {}

        total_hours = 0.0
        total_billable = 0.0
        total_amount = 0.0
        rows: list[TogglProjectRow] = []

        for group in all_summary:
            pid = group.get("id", 0)
            proj = proj_map.get(pid, {})
            sub_groups = group.get("sub_groups") or group.get("items") or []

            group_hours = 0.0
            for item in sub_groups:
                rates = item.get("rates") or []
                for rate_info in rates:
                    secs = rate_info.get("billable_seconds", 0) or 0
                    group_hours += secs / 3600
                secs_total = item.get("seconds", 0) or item.get("time", 0) or 0
                if not rates:
                    group_hours += secs_total / 3600
                elif secs_total / 3600 > group_hours:
                    group_hours = secs_total / 3600

            if group_hours <= 0:
                continue

            b_hours, b_amount, b_rate = billable_by_pid.get(pid, (0, 0, 0))
            is_billable = b_hours > 0
            cid = proj.get("client_id")
            client_name = client_map.get(cid, "") if cid else ""

            budget_key = str(pid)
            budget_cfg = budgets.get(budget_key) or (budgets.get(str(cid)) if cid else None) or {}
            budget_hours = budget_cfg.get("monthly_hours") if budget_cfg else None

            budget_pct = None
            if budget_hours and budget_hours > 0:
                budget_pct = round(group_hours / budget_hours * 100, 1)

            total_hours += group_hours
            total_billable += b_hours
            total_amount += b_amount

            rows.append(TogglProjectRow(
                project_id=pid,
                project_name=proj.get("name") or f"Projekt {pid}",
                client_id=cid,
                client_name=client_name,
                hours=round(group_hours, 1),
                billable_hours=round(b_hours, 1),
                is_billable=is_billable,
                rate_per_hour=round(b_rate, 2),
                amount=round(b_amount, 2),
                budget_hours=budget_hours,
                budget_pct=budget_pct,
            ))

        # Prozent-Anteile berechnen
        for row in rows:
            if total_hours > 0:
                row.pct_of_total = round(row.hours / total_hours * 100, 1)

        rows.sort(key=lambda x: x.hours, reverse=True)

        wd_total = _working_days_in_month(today.year, today.month)
        wd_elapsed = _working_days_elapsed(today.year, today.month)

        avg_daily = total_hours / wd_elapsed if wd_elapsed > 0 else 0
        billable_daily = total_billable / wd_elapsed if wd_elapsed > 0 else 0
        rate_avg = total_amount / total_billable if total_billable > 0 else 0
        forecast_amount = billable_daily * wd_total * rate_avg if wd_elapsed > 0 else 0

        toggl_month = TogglMonthSummary(
            total_hours=round(total_hours, 1),
            billable_hours=round(total_billable, 1),
            non_billable_hours=round(total_hours - total_billable, 1),
            billable_ratio=round(total_billable / total_hours * 100, 1) if total_hours > 0 else 0,
            total_amount=round(total_amount, 2),
            avg_daily_hours=round(avg_daily, 1),
            forecast_month_amount=round(forecast_amount, 2),
            working_days_total=wd_total,
            working_days_elapsed=wd_elapsed,
            projects=rows,
        )
    except Exception as e:
        logger.warning("Toggl-Daten nicht verfuegbar: %s", e)

    # ── Bexio: Debitoren ─────────────────────────────────
    debtors: list[DebtorSummary] = []
    revenue_trend: list[RevenueByMonth] = []
    total_open = 0.0
    total_revenue_ytd = 0.0
    dso_days = None

    try:
        bexio = _get_bexio_client(user)

        contact_list = await bexio.list_contacts(limit=200)
        contact_names = {c.get("id", 0): f"{c.get('name_1', '')} {c.get('name_2', '') or ''}".strip() for c in contact_list}

        all_invoices = await _fetch_invoices(bexio, months=25)

        # Pro Kontakt aggregieren
        by_contact: dict[int, dict] = defaultdict(lambda: {
            "revenue_ytd": 0.0, "revenue_prior": 0.0,
            "open_count": 0, "open_total": 0.0,
            "payment_days": [], "projects": set(),
            "aging_0_30": 0.0, "aging_31_60": 0.0,
            "aging_61_90": 0.0, "aging_over_90": 0.0,
            "by_month": defaultdict(float),
        })

        for inv in all_invoices:
            cid = inv.get("contact_id")
            if not cid:
                continue

            total = _parse_invoice_total(inv)
            inv_date_str = inv.get("is_valid_from") or ""

            if len(inv_date_str) >= 7:
                month_key = inv_date_str[:7]
                by_contact[cid]["by_month"][month_key] += total

                if month_key.startswith(str(current_year)):
                    by_contact[cid]["revenue_ytd"] += total
                elif month_key.startswith(str(prior_year)):
                    by_contact[cid]["revenue_prior"] += total

            if _invoice_is_open(inv):
                remaining = _open_amount(inv)
                by_contact[cid]["open_count"] += 1
                by_contact[cid]["open_total"] += remaining

                if inv_date_str:
                    try:
                        inv_date = date.fromisoformat(inv_date_str[:10])
                        age = (today - inv_date).days
                        if age <= 30:
                            by_contact[cid]["aging_0_30"] += remaining
                        elif age <= 60:
                            by_contact[cid]["aging_31_60"] += remaining
                        elif age <= 90:
                            by_contact[cid]["aging_61_90"] += remaining
                        else:
                            by_contact[cid]["aging_over_90"] += remaining
                    except (ValueError, TypeError):
                        by_contact[cid]["aging_0_30"] += remaining

        # Debtors-Liste aufbauen
        for cid, data in by_contact.items():
            if data["revenue_ytd"] <= 0 and data["open_total"] <= 0 and data["revenue_prior"] <= 0:
                continue

            name = contact_names.get(cid, f"Kontakt {cid}")
            rev_ytd = data["revenue_ytd"]
            rev_prior = data["revenue_prior"]
            delta_pct = None
            if rev_prior > 0:
                delta_pct = round((rev_ytd - rev_prior) / rev_prior * 100, 1)

            total_open += data["open_total"]
            total_revenue_ytd += rev_ytd

            debtors.append(DebtorSummary(
                contact_id=cid,
                contact_name=name,
                revenue_ytd=round(rev_ytd, 2),
                revenue_prior_year=round(rev_prior, 2),
                revenue_delta_pct=delta_pct,
                open_invoices_count=data["open_count"],
                open_invoices_total=round(data["open_total"], 2),
                aging_0_30=round(data["aging_0_30"], 2),
                aging_31_60=round(data["aging_31_60"], 2),
                aging_61_90=round(data["aging_61_90"], 2),
                aging_over_90=round(data["aging_over_90"], 2),
            ))

        debtors.sort(key=lambda x: x.revenue_ytd, reverse=True)

        # DSO berechnen
        months_elapsed = today.month
        if total_revenue_ytd > 0 and months_elapsed > 0:
            daily_rev = total_revenue_ytd / (months_elapsed * 30)
            if daily_rev > 0:
                dso_days = round(total_open / daily_rev, 0)

        # Revenue-Trend: Top-5-Kunden, letzte 12 Monate
        top_contacts = sorted(by_contact.items(), key=lambda x: x[1]["revenue_ytd"], reverse=True)[:5]
        for cid, data in top_contacts:
            if not data["by_month"]:
                continue
            revenue_trend.append(RevenueByMonth(
                contact_id=cid,
                contact_name=contact_names.get(cid, f"Kontakt {cid}"),
                months=dict(sorted(data["by_month"].items())[-12:]),
            ))

    except Exception as e:
        logger.warning("Bexio-Debitoren nicht verfuegbar: %s", e)

    result = DebtorsResponse(
        toggl_month=toggl_month,
        debtors=debtors,
        revenue_trend=revenue_trend,
        total_open=round(total_open, 2),
        total_revenue_ytd=round(total_revenue_ytd, 2),
        dso_days=dso_days,
    )
    _cache["debtors"] = result
    return result


@router.post("/cache/clear")
async def clear_cache(user: User = Depends(get_current_user)):
    _cache.clear()
    logger.info("Debtors-Cache manuell geleert")
    return {"status": "ok", "message": "Debtors-Cache geleert"}
