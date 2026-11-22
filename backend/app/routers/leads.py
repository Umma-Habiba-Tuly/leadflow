import csv
import io
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Lead
from app.db.session import get_db
from app.deps import Principal, get_principal
from app.routers.campaigns import get_owned_campaign
from app.schemas import ImportResult, LeadList
from app.services.leads import IngestItem, ingest_leads

router = APIRouter(tags=["leads"])

MAX_CSV_BYTES = 5 * 1024 * 1024


def _to_float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _to_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(float(value)) if value not in (None, "") else None
    except ValueError:
        return None


@router.get("/campaigns/{campaign_id}/leads", response_model=LeadList)
def list_leads(
    campaign_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: Literal["id", "score"] = Query("id", description="'score' lists best-scored leads first"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    campaign = get_owned_campaign(db, campaign_id, principal)
    where = (Lead.campaign_id == campaign.id, Lead.workspace_id == principal.workspace_id)
    total = db.scalar(select(func.count()).select_from(Lead).where(*where)) or 0
    order = (Lead.score.desc().nulls_last(), Lead.id) if sort == "score" else (Lead.id,)
    items = list(db.scalars(select(Lead).where(*where).order_by(*order).limit(limit).offset(offset)))
    return LeadList(total=total, items=items)


@router.post("/campaigns/{campaign_id}/leads/import", response_model=ImportResult)
async def import_csv(
    campaign_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """Import leads from CSV. Columns: name (required), website, phone, address, email,
    rating, review_count."""
    campaign = get_owned_campaign(db, campaign_id, principal)

    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "CSV larger than 5 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV must be UTF-8")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "name" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV needs a 'name' column")

    items = []
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        key = row.get("email") or row.get("website") or row.get("name", "")
        items.append(
            IngestItem(
                source="csv",
                source_id=key.lower(),
                name=row.get("name", ""),
                website=row.get("website") or None,
                phone=row.get("phone") or None,
                address=row.get("address") or None,
                email=row.get("email") or None,
                rating=_to_float(row.get("rating")),
                review_count=_to_int(row.get("review_count")),
            )
        )

    stats = ingest_leads(db, campaign, items)
    return ImportResult(**stats.__dict__)
