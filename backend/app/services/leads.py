from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Campaign, Lead, Suppression


@dataclass
class IngestItem:
    source: str
    source_id: str
    name: str
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None


@dataclass
class IngestStats:
    added: int = 0
    skipped_duplicates: int = 0
    skipped_suppressed: int = 0
    skipped_invalid: int = 0


def ingest_leads(db: Session, campaign: Campaign, items: Iterable[IngestItem]) -> IngestStats:
    """Insert leads into a campaign, skipping duplicates and suppressed emails.

    Every query is scoped by campaign.workspace_id so tenants never see each other's data.
    """
    ws = campaign.workspace_id
    stats = IngestStats()

    suppressed = {
        e.lower()
        for e in db.scalars(select(Suppression.email).where(Suppression.workspace_id == ws))
    }
    seen = {
        (s, sid)
        for s, sid in db.execute(
            select(Lead.source, Lead.source_id).where(Lead.campaign_id == campaign.id)
        )
    }

    for item in items:
        name = (item.name or "").strip()
        if not name or not item.source_id:
            stats.skipped_invalid += 1
            continue
        email = item.email.strip().lower() if item.email else None
        if email and email in suppressed:
            stats.skipped_suppressed += 1
            continue
        key = (item.source, item.source_id)
        if key in seen:
            stats.skipped_duplicates += 1
            continue
        seen.add(key)

        db.add(
            Lead(
                workspace_id=ws,
                campaign_id=campaign.id,
                name=name,
                website=item.website,
                phone=item.phone,
                address=item.address,
                email=email,
                rating=item.rating,
                review_count=item.review_count,
                source=item.source,
                source_id=item.source_id,
            )
        )
        stats.added += 1

    db.commit()
    return stats


def suppress_email(db: Session, workspace_id: int, email: str, reason: str = "unsubscribed") -> Suppression:
    """Put an email on the do-not-contact list and flag every existing lead that uses it.

    Single place for this rule, used by the API and by the public unsubscribe link.
    """
    email = email.strip().lower()
    existing = db.scalar(
        select(Suppression).where(Suppression.workspace_id == workspace_id, Suppression.email == email)
    )
    if existing is None:
        existing = Suppression(workspace_id=workspace_id, email=email, reason=reason)
        db.add(existing)
    for lead in db.scalars(select(Lead).where(Lead.workspace_id == workspace_id, Lead.email == email)):
        lead.status = "do_not_contact"
    db.commit()
    return existing
