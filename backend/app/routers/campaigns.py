from datetime import datetime, timezone
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Campaign, Lead, Suppression
from app.db.session import get_db
from app.deps import Principal, get_principal
from app.providers.places import PlacesNotConfigured, search_places
from app.schemas import (
    CampaignIn,
    CampaignOut,
    EnrichIn,
    EnrichResult,
    ImportResult,
    ScoreIn,
    ScoreSummary,
    SearchIn,
)
from app.services import enrichment, scoring
from app.services.leads import IngestItem, ingest_leads
from app.services.llm import LLMClient, LLMError, LLMNotConfigured, LLMRateLimited, get_llm_client

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def get_owned_campaign(db: Session, campaign_id: int, principal: Principal) -> Campaign:
    campaign = db.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.workspace_id == principal.workspace_id
        )
    )
    if campaign is None:
        # 404 (not 403) so we never reveal that another tenant's campaign exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return campaign


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(
    body: CampaignIn, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)
):
    campaign = Campaign(workspace_id=principal.workspace_id, **body.model_dump())
    db.add(campaign)
    db.commit()
    return campaign


@router.get("", response_model=List[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    return list(
        db.scalars(
            select(Campaign)
            .where(Campaign.workspace_id == principal.workspace_id)
            .order_by(Campaign.id.desc())
        )
    )


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    return get_owned_campaign(db, campaign_id, principal)


@router.post("/{campaign_id}/search", response_model=ImportResult)
def run_search(
    campaign_id: int,
    body: SearchIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """Find businesses via Google Places for this campaign's niche + location."""
    campaign = get_owned_campaign(db, campaign_id, principal)
    try:
        raw = search_places(campaign.niche, campaign.location, body.max_results)
    except PlacesNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Places API error: {exc}")

    stats = ingest_leads(
        db,
        campaign,
        [
            IngestItem(
                source="google_places",
                source_id=r.source_id,
                name=r.name,
                website=r.website,
                phone=r.phone,
                address=r.address,
                rating=r.rating,
                review_count=r.review_count,
            )
            for r in raw
        ],
    )
    return ImportResult(**stats.__dict__)


@router.post("/{campaign_id}/enrich", response_model=EnrichResult)
def enrich_campaign(
    campaign_id: int,
    body: EnrichIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """Find contact emails on lead websites. Processes up to `limit` leads per call.

    Only leads that have a website, no email yet, and haven't been tried before.
    (Runs inline for now; moves to a background job once we add a queue.)
    """
    campaign = get_owned_campaign(db, campaign_id, principal)
    leads = list(
        db.scalars(
            select(Lead)
            .where(
                Lead.campaign_id == campaign.id,
                Lead.workspace_id == principal.workspace_id,
                Lead.email.is_(None),
                Lead.website.is_not(None),
                Lead.enriched_at.is_(None),
            )
            .order_by(Lead.id)
            .limit(body.limit)
        )
    )
    suppressed = {
        e.lower()
        for e in db.scalars(
            select(Suppression.email).where(Suppression.workspace_id == principal.workspace_id)
        )
    }

    result = EnrichResult(checked=0, found=0, not_found=0, suppressed=0)
    for lead in leads:
        email = enrichment.find_email_for_site(lead.website)
        lead.enriched_at = datetime.now(timezone.utc)
        result.checked += 1
        if email is None:
            result.not_found += 1
        elif email in suppressed:
            lead.status = "do_not_contact"
            result.suppressed += 1
        else:
            lead.email = email
            result.found += 1

    db.commit()
    return result


@router.post("/{campaign_id}/score", response_model=ScoreSummary)
def score_campaign(
    campaign_id: int,
    body: ScoreIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    llm: LLMClient = Depends(get_llm_client),
):
    """AI-score up to `limit` unscored leads (0-100 + a short reason).

    Leads on the do-not-contact list are skipped so we never spend tokens on them.
    If the model rate-limits us, we keep what we already scored and report it.
    """
    campaign = get_owned_campaign(db, campaign_id, principal)
    pending = (
        Lead.campaign_id == campaign.id,
        Lead.workspace_id == principal.workspace_id,
        Lead.scored_at.is_(None),
        Lead.status != "do_not_contact",
    )
    leads = list(db.scalars(select(Lead).where(*pending).order_by(Lead.id).limit(body.limit)))

    summary = ScoreSummary(scored=0, failed=0, rate_limited=False, remaining=0)
    try:
        for lead in leads:
            try:
                result = scoring.score_lead(llm, campaign, lead)
            except LLMNotConfigured as exc:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
            except LLMRateLimited:
                summary.rate_limited = True
                break
            except LLMError as exc:
                summary.failed += 1  # leave scored_at empty so it can be retried later
                summary.last_error = str(exc)
                continue
            lead.score = result.score
            lead.score_reason = result.reason
            lead.scored_at = datetime.now(timezone.utc)
            summary.scored += 1
    finally:
        db.commit()  # keep partial progress even if we bail out

    summary.remaining = (
        db.scalar(select(func.count()).select_from(Lead).where(*pending)) or 0
    )
    return summary
