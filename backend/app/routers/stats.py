"""Small read-only endpoints the dashboard needs."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Draft, Lead, SentEmail, User, Workspace
from app.db.session import get_db
from app.deps import Principal, get_principal
from app.routers.campaigns import get_owned_campaign
from app.routers.drafts import _eligible
from app.schemas import CampaignStats, MeOut
from app.services.compliance import missing_profile_fields

router = APIRouter(tags=["dashboard"])


@router.get("/auth/me", response_model=MeOut)
def me(db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    user = db.get(User, principal.user_id)
    workspace = db.get(Workspace, principal.workspace_id)
    missing = missing_profile_fields(workspace)
    return MeOut(email=user.email, workspace_name=workspace.name, profile_complete=not missing, profile_missing=missing)


@router.get("/campaigns/{campaign_id}/stats", response_model=CampaignStats)
def campaign_stats(campaign_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    campaign = get_owned_campaign(db, campaign_id, principal)
    ws = principal.workspace_id
    in_campaign = (Lead.campaign_id == campaign.id, Lead.workspace_id == ws)

    def count(*conditions, table=Lead):
        return db.scalar(select(func.count()).select_from(table).where(*conditions)) or 0

    drafts_in = (Draft.workspace_id == ws, Draft.lead_id.in_(select(Lead.id).where(*in_campaign)))
    return CampaignStats(
        leads=count(*in_campaign),
        with_email=count(*in_campaign, Lead.email.is_not(None)),
        scored=count(*in_campaign, Lead.score.is_not(None)),
        drafts=count(*drafts_in, table=Draft),
        approved=count(*drafts_in, Draft.status == "approved", table=Draft),
        sent=count(
            SentEmail.workspace_id == ws, SentEmail.status == "sent",
            SentEmail.lead_id.in_(select(Lead.id).where(*in_campaign)), table=SentEmail,
        ),
        opted_out=count(*in_campaign, Lead.status == "do_not_contact"),
        to_enrich=count(*in_campaign, Lead.email.is_(None), Lead.website.is_not(None), Lead.enriched_at.is_(None)),
        to_score=count(*in_campaign, Lead.scored_at.is_(None), Lead.status != "do_not_contact"),
        to_draft=count(*_eligible(campaign.id, ws, 50)),
        to_review=count(*drafts_in, Draft.status == "draft", table=Draft),
        # Same rule the sender uses: a draft that already has a send record (sent, refused or in flight) never goes out again.
        to_send=count(*drafts_in, Draft.status == "approved", Draft.id.not_in(select(SentEmail.draft_id)), table=Draft),
    )
