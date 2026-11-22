from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Draft, Lead, Workspace
from app.db.session import get_db
from app.deps import Principal, get_principal
from app.routers.campaigns import get_owned_campaign
from app.schemas import DraftGenerateIn, DraftGenerateSummary, DraftOut, DraftPatch
from app.services import compliance, email_draft
from app.services.llm import LLMClient, LLMError, LLMNotConfigured, LLMRateLimited, get_llm_client

router = APIRouter(tags=["drafts"])


def _to_out(draft: Draft, lead: Lead, workspace: Workspace) -> DraftOut:
    unsub = compliance.unsubscribe_url(workspace.id, lead.email)
    return DraftOut(
        id=draft.id,
        lead_id=lead.id,
        lead_name=lead.name,
        to_email=lead.email,
        subject=draft.subject,
        body=draft.body,
        status=draft.status,
        preview=compliance.compose_email_text(draft.body, workspace, unsub),
    )


def _eligible(campaign_id: int, workspace_id: int, min_score: int):
    """Leads that deserve a draft: reachable, not opted out, scored well, no draft yet."""
    already_drafted = select(Draft.lead_id).where(Draft.workspace_id == workspace_id)
    return (
        Lead.campaign_id == campaign_id,
        Lead.workspace_id == workspace_id,
        Lead.email.is_not(None),
        Lead.status != "do_not_contact",
        Lead.score.is_not(None),
        Lead.score >= min_score,
        Lead.id.not_in(already_drafted),
    )


@router.post("/campaigns/{campaign_id}/drafts/generate", response_model=DraftGenerateSummary)
def generate_drafts(
    campaign_id: int,
    body: DraftGenerateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    llm: LLMClient = Depends(get_llm_client),
):
    """AI-write up to `limit` email drafts, best-scored leads first."""
    campaign = get_owned_campaign(db, campaign_id, principal)
    workspace = db.get(Workspace, principal.workspace_id)

    missing = compliance.missing_profile_fields(workspace)
    if missing:
        # Refuse up front: we never create emails that couldn't legally be sent.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Complete your sender profile first (missing: {', '.join(missing)})",
        )

    where = _eligible(campaign.id, workspace.id, body.min_score)
    leads = list(
        db.scalars(select(Lead).where(*where).order_by(Lead.score.desc(), Lead.id).limit(body.limit))
    )

    summary = DraftGenerateSummary(generated=0, failed=0, rate_limited=False, remaining=0)
    try:
        for lead in leads:
            try:
                text = email_draft.generate_draft(llm, campaign, lead, workspace)
            except LLMNotConfigured as exc:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
            except LLMRateLimited:
                summary.rate_limited = True
                break
            except LLMError as exc:
                summary.failed += 1
                summary.last_error = str(exc)
                continue
            db.add(Draft(workspace_id=workspace.id, lead_id=lead.id, subject=text.subject, body=text.body))
            summary.generated += 1
    finally:
        db.commit()

    summary.remaining = db.scalar(select(func.count()).select_from(Lead).where(*where)) or 0
    return summary


@router.get("/campaigns/{campaign_id}/drafts", response_model=List[DraftOut])
def list_drafts(
    campaign_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)
):
    campaign = get_owned_campaign(db, campaign_id, principal)
    workspace = db.get(Workspace, principal.workspace_id)
    rows = db.execute(
        select(Draft, Lead)
        .join(Lead, Lead.id == Draft.lead_id)
        .where(Lead.campaign_id == campaign.id, Draft.workspace_id == principal.workspace_id)
        .order_by(Lead.score.desc(), Draft.id)
    ).all()
    return [_to_out(d, l, workspace) for d, l in rows]


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
def edit_or_approve_draft(
    draft_id: int,
    body: DraftPatch,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """Edit the message and/or approve it. Editing sends a draft back to 'draft' status,
    so what gets approved is always exactly what the human last read."""
    draft = db.scalar(
        select(Draft).where(Draft.id == draft_id, Draft.workspace_id == principal.workspace_id)
    )
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    lead = db.get(Lead, draft.lead_id)
    workspace = db.get(Workspace, principal.workspace_id)

    if body.subject is not None or body.body is not None:
        try:
            # A human wrote this, so links are allowed. Length/placeholder/deception rules still apply.
            text = email_draft.validate_draft(
                body.subject if body.subject is not None else draft.subject,
                body.body if body.body is not None else draft.body,
                allow_links=True,
            )
        except LLMError as exc:
            raise HTTPException(422, str(exc))  # literal: the constant's name changed across Starlette versions
        draft.subject, draft.body, draft.status = text.subject, text.body, "draft"

    if body.approved is True:
        if lead.status == "do_not_contact" or not lead.email:
            raise HTTPException(status.HTTP_409_CONFLICT, "This lead can no longer be contacted")
        draft.status = "approved"
    elif body.approved is False:
        draft.status = "draft"

    db.commit()
    return _to_out(draft, lead, workspace)
