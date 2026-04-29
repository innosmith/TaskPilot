"""FastAPI Router fuer Pipedrive CRM-Daten (Frontend-Zugriff).

Stellt die Pipedrive-Daten dem Frontend ueber REST-Endpunkte bereit,
ohne dass das Frontend direkt mit der Pipedrive-API kommunizieren muss.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.models import User

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "pipedrive"))
from pipedrive_client import PipedriveClient, PipedriveConfig  # noqa: E402

router = APIRouter(prefix="/api/pipedrive", tags=["pipedrive"])


def _get_pipedrive_client(user: User) -> PipedriveClient:
    """Pipedrive-Client aus User-Settings oder Env-Variablen erstellen."""
    settings = user.settings or {}
    token = settings.get("pipedrive_api_token") or ""
    domain = settings.get("pipedrive_domain") or "innosmith"

    if not token:
        from app.config import get_settings
        app_cfg = get_settings()
        token = app_cfg.pipedrive_api_token
        domain = app_cfg.pipedrive_domain or domain

    if not token:
        raise HTTPException(status_code=400, detail="Pipedrive API-Token nicht konfiguriert")

    return PipedriveClient(PipedriveConfig(api_token=token, company_domain=domain))


# ── Verbindungstest ──────────────────────────────────────

@router.get("/test-connection")
async def test_connection(user: User = Depends(get_current_user)):
    import logging
    logger = logging.getLogger("taskpilot.pipedrive")
    try:
        client = _get_pipedrive_client(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Pipedrive Client-Erstellung fehlgeschlagen: %s", e)
        raise HTTPException(status_code=400, detail=f"Client-Fehler: {e}")
    try:
        result = await client.test_connection()
        return result
    except Exception as e:
        logger.error("Pipedrive Verbindungstest fehlgeschlagen: %s", e)
        raise HTTPException(status_code=502, detail=f"Verbindung fehlgeschlagen: {e}")


# ── Deals ────────────────────────────────────────────────

class DealSummary(BaseModel):
    id: int
    title: str
    status: str | None = None
    value: float | None = None
    currency: str | None = None
    stage_id: int | None = None
    person_name: str | None = None
    org_name: str | None = None


@router.get("/deals", response_model=list[DealSummary])
async def list_deals(
    pipeline_id: int | None = None,
    stage_id: int | None = None,
    status: str = "open",
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
):
    client = _get_pipedrive_client(user)
    deals = await client.list_deals(
        pipeline_id=pipeline_id, stage_id=stage_id, status=status, limit=limit
    )
    return [DealSummary(**{k: d.get(k) for k in DealSummary.model_fields}) for d in deals]


@router.get("/deals/{deal_id}")
async def get_deal(deal_id: int, user: User = Depends(get_current_user)):
    client = _get_pipedrive_client(user)
    return await client.get_deal(deal_id)


# ── Leads ────────────────────────────────────────────────

class LeadSummary(BaseModel):
    id: str
    title: str
    person_id: int | None = None
    person_name: str | None = None
    organization_id: int | None = None
    org_name: str | None = None
    expected_close_date: str | None = None
    value: float | None = None
    currency: str | None = None


@router.get("/leads", response_model=list[LeadSummary])
async def list_leads(
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
):
    client = _get_pipedrive_client(user)
    leads = await client.list_leads(limit=limit)
    result = []
    for lead in leads:
        val = lead.get("value") or {}
        result.append(LeadSummary(
            id=lead.get("id", ""),
            title=lead.get("title", ""),
            person_id=lead.get("person_id"),
            person_name=lead.get("person_name"),
            organization_id=lead.get("organization_id"),
            org_name=lead.get("organization_name"),
            expected_close_date=lead.get("expected_close_date"),
            value=val.get("amount") if isinstance(val, dict) else None,
            currency=val.get("currency") if isinstance(val, dict) else None,
        ))
    return result


# ── Persons ──────────────────────────────────────────────

class PersonSummary(BaseModel):
    id: int
    name: str
    email: str | None = None
    org_name: str | None = None


@router.get("/persons", response_model=list[PersonSummary])
async def list_persons(
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
):
    client = _get_pipedrive_client(user)
    persons = await client.list_persons(limit=limit)
    result = []
    for p in persons:
        emails = p.get("email", [])
        email_str = emails[0].get("value", "") if isinstance(emails, list) and emails else ""
        result.append(PersonSummary(
            id=p.get("id"), name=p.get("name", ""), email=email_str,
            org_name=p.get("org_name"),
        ))
    return result


@router.get("/persons/{person_id}")
async def get_person(person_id: int, user: User = Depends(get_current_user)):
    client = _get_pipedrive_client(user)
    return await client.get_person(person_id)


# ── Activities ───────────────────────────────────────────

class ActivitySummary(BaseModel):
    id: int
    subject: str
    type: str | None = None
    done: bool | None = None
    due_date: str | None = None
    deal_id: int | None = None
    person_name: str | None = None


@router.get("/activities", response_model=list[ActivitySummary])
async def list_activities(
    done: bool | None = None,
    deal_id: int | None = None,
    person_id: int | None = None,
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
):
    client = _get_pipedrive_client(user)
    acts = await client.list_activities(done=done, deal_id=deal_id, person_id=person_id, limit=limit)
    return [ActivitySummary(**{k: a.get(k) for k in ActivitySummary.model_fields}) for a in acts]


# ── Pipelines & Stages ──────────────────────────────────

class PipelineSummary(BaseModel):
    id: int
    name: str
    active: bool | None = None


class StageSummary(BaseModel):
    id: int
    name: str
    pipeline_id: int | None = None
    order_nr: int | None = None


@router.get("/pipelines", response_model=list[PipelineSummary])
async def list_pipelines(user: User = Depends(get_current_user)):
    client = _get_pipedrive_client(user)
    pls = await client.list_pipelines()
    return [PipelineSummary(**{k: p.get(k) for k in PipelineSummary.model_fields}) for p in pls]


@router.get("/pipelines/{pipeline_id}/stages", response_model=list[StageSummary])
async def list_stages(pipeline_id: int, user: User = Depends(get_current_user)):
    client = _get_pipedrive_client(user)
    stages = await client.list_stages(pipeline_id=pipeline_id)
    return [StageSummary(**{k: s.get(k) for k in StageSummary.model_fields}) for s in stages]


# ── Pipeline-Summary (aggregiert) ────────────────────────

@router.get("/pipeline-summary")
async def get_pipeline_summary(
    pipeline_id: int | None = None,
    user: User = Depends(get_current_user),
):
    client = _get_pipedrive_client(user)
    return await client.get_pipeline_summary(pipeline_id=pipeline_id)


# ── Suche ────────────────────────────────────────────────

@router.get("/search")
async def search_crm(
    term: str = Query(min_length=1),
    item_types: str = "deal,person,organization",
    limit: int = Query(default=10, le=50),
    user: User = Depends(get_current_user),
):
    client = _get_pipedrive_client(user)
    return await client.search_items(term, item_types, limit)


# ── E-Mail-Lookup ────────────────────────────────────────

class PersonLookupResult(BaseModel):
    id: int
    name: str
    email: str | None = None
    org_name: str | None = None
    org_id: int | None = None
    phone: str | None = None
    pic_url: str | None = None
    open_deals_count: int = 0
    open_deals: list[DealSummary] = []


def _extract_pic_url(person: dict) -> str | None:
    """Profilbild-URL robust aus Pipedrive Person-Daten extrahieren."""
    pic = person.get("picture_id") or person.get("picture") or {}
    if isinstance(pic, dict):
        pics = pic.get("pictures", {})
        if isinstance(pics, dict):
            return pics.get("128") or pics.get("512") or pics.get("small") or None
        url = pic.get("url") or pic.get("value") or None
        if url:
            return url
    if isinstance(pic, str) and pic.startswith("http"):
        return pic
    pic_url_direct = person.get("pic_url") or person.get("picture_url") or None
    if pic_url_direct:
        return pic_url_direct
    return None


def _extract_email(person: dict) -> str:
    """Primaere E-Mail-Adresse robust aus Person extrahieren."""
    emails_raw = person.get("email", [])
    if isinstance(emails_raw, list) and emails_raw:
        first = emails_raw[0]
        return first.get("value", "") if isinstance(first, dict) else str(first)
    if isinstance(emails_raw, str):
        return emails_raw
    return person.get("primary_email", "") or ""


def _extract_phone(person: dict) -> str:
    """Primaere Telefonnummer aus Person extrahieren."""
    phones = person.get("phone", [])
    if isinstance(phones, list) and phones:
        first = phones[0]
        return first.get("value", "") if isinstance(first, dict) else str(first)
    return ""


@router.get("/lookup-email", response_model=PersonLookupResult | None)
async def lookup_email(
    email: str = Query(min_length=3),
    user: User = Depends(get_current_user),
):
    """Person in Pipedrive anhand der E-Mail-Adresse suchen."""
    import logging
    logger = logging.getLogger("taskpilot.pipedrive")
    client = _get_pipedrive_client(user)

    person_id: int | None = None

    try:
        results = await client.search_persons_by_email(email, 5)
        for item in results:
            item_data = item.get("item", item)
            pid = item_data.get("id")
            if pid:
                person_id = pid
                break
    except Exception as exc:
        logger.debug("search_persons_by_email fehlgeschlagen: %s", exc)

    if not person_id:
        try:
            results = await client.search_items(email, "person", 5)
            for item in results:
                item_data = item.get("item", item)
                pid = item_data.get("id")
                if pid:
                    person_id = pid
                    break
        except Exception as exc:
            logger.debug("search_items fallback fehlgeschlagen: %s", exc)

    if not person_id:
        return None

    try:
        person = await client.get_person_v1(person_id)
    except Exception:
        return None

    person_email = _extract_email(person)
    phone = _extract_phone(person)
    pic_url = _extract_pic_url(person)

    org = person.get("org_id") or {}
    org_name = org.get("name") if isinstance(org, dict) else person.get("org_name", "")
    org_id = org.get("value") if isinstance(org, dict) else None

    try:
        deals = await client.list_deals(limit=20)
        person_deals = [
            DealSummary(**{k: d.get(k) for k in DealSummary.model_fields})
            for d in deals
            if d.get("person_id") == person_id or d.get("person_name") == person.get("name")
        ]
    except Exception:
        person_deals = []

    return PersonLookupResult(
        id=person_id,
        name=person.get("name", ""),
        email=person_email,
        org_name=org_name,
        org_id=org_id,
        phone=phone,
        pic_url=pic_url,
        open_deals_count=len(person_deals),
        open_deals=person_deals[:3],
    )


# ── Quick-Contact ────────────────────────────────────────

class QuickContactRequest(BaseModel):
    name: str
    email: str
    org_name: str | None = None
    phone: str | None = None


class QuickContactResponse(BaseModel):
    id: int
    name: str


@router.post("/quick-contact", response_model=QuickContactResponse)
async def create_quick_contact(
    body: QuickContactRequest,
    user: User = Depends(get_current_user),
):
    """Neuen Kontakt in Pipedrive anlegen."""
    client = _get_pipedrive_client(user)

    kwargs: dict = {"email": [{"value": body.email, "primary": True, "label": "work"}]}
    if body.phone:
        kwargs["phone"] = [{"value": body.phone, "primary": True, "label": "work"}]

    if body.org_name:
        orgs = await client.search_items(body.org_name, "organization", 1)
        if orgs:
            org_data = orgs[0].get("item", orgs[0])
            kwargs["org_id"] = org_data.get("id")
        else:
            pass

    person = await client.create_person(body.name, **kwargs)
    return QuickContactResponse(id=person.get("id", 0), name=person.get("name", body.name))
