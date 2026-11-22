"""Send approved drafts safely.

Order of safety, each one a separate guard:
  dry-run by default, daily cap, opt-out re-check at the last moment, claim-before-send
  (never double-email), stop on config/network errors, auto-pause on too many rejected addresses.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Campaign, Draft, Lead, Mailbox, SentEmail, Suppression, Workspace
from app.services import compliance
from app.services.email_sender import EmailSender, OutgoingEmail, SendError
from app.services.leads import suppress_email

BATCH_MAX = 20  # per request: sending is synchronous until background jobs exist
BOUNCE_WINDOW = 50  # look at the mailbox's most recent attempts...
BOUNCE_MIN_ATTEMPTS = 10  # ...once there are enough to mean something...
BOUNCE_PAUSE_RATE = 0.10  # ...and pause the mailbox if this share was refused outright


@dataclass
class SendReport:
    dry_run: bool
    sent: int = 0
    rejected: int = 0
    skipped_opted_out: int = 0
    quota_remaining: int = 0
    mailbox_paused: bool = False
    stopped_reason: Optional[str] = None
    would_send: List[dict] = field(default_factory=list)


def _start_of_utc_day() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def count_today(db: Session, mailbox_id: int) -> int:
    """Every attempt today counts (sent, in flight, or refused): all of them hit the server."""
    return db.scalar(
        select(func.count()).select_from(SentEmail).where(
            SentEmail.mailbox_id == mailbox_id, SentEmail.created_at >= _start_of_utc_day()
        )
    ) or 0


def _should_pause(db: Session, mailbox: Mailbox) -> bool:
    recent = list(
        db.scalars(
            select(SentEmail.status)
            .where(SentEmail.mailbox_id == mailbox.id, SentEmail.status.in_(["sent", "rejected"]))
            .order_by(SentEmail.id.desc())
            .limit(BOUNCE_WINDOW)
        )
    )
    if len(recent) < BOUNCE_MIN_ATTEMPTS:
        return False
    return recent.count("rejected") / len(recent) >= BOUNCE_PAUSE_RATE


def send_batch(
    db: Session, *, campaign: Campaign, workspace: Workspace, mailbox: Mailbox,
    sender: EmailSender, limit: int, dry_run: bool,
) -> SendReport:
    report = SendReport(dry_run=dry_run)
    quota = mailbox.daily_limit - count_today(db, mailbox.id)
    report.quota_remaining = max(quota, 0)
    if quota <= 0:
        report.stopped_reason = "daily limit reached for this mailbox"
        return report

    already_claimed = select(SentEmail.draft_id)
    rows = db.execute(
        select(Draft, Lead)
        .join(Lead, Lead.id == Draft.lead_id)
        .where(
            Draft.workspace_id == workspace.id,
            Lead.campaign_id == campaign.id,
            Draft.status == "approved",
            Lead.status != "do_not_contact",
            Lead.email.is_not(None),
            Draft.id.not_in(already_claimed),
        )
        .order_by(Draft.id)
        .limit(min(limit, quota, BATCH_MAX))
    ).all()

    # Checked again here, right before sending: someone may have unsubscribed after approval.
    opted_out = {
        e.lower() for e in db.scalars(select(Suppression.email).where(Suppression.workspace_id == workspace.id))
    }

    for draft, lead in rows:
        email = lead.email.lower()
        if email in opted_out:
            report.skipped_opted_out += 1
            continue

        text = compliance.compose_email_text(draft.body, workspace, compliance.unsubscribe_url(workspace.id, email))
        if dry_run:
            report.would_send.append({"draft_id": draft.id, "to_email": email, "subject": draft.subject})
            continue

        # Claim first. UNIQUE(draft_id) means two requests can never both send this draft.
        claim = SentEmail(
            workspace_id=workspace.id, draft_id=draft.id, lead_id=lead.id, mailbox_id=mailbox.id,
            to_email=email, subject=draft.subject, status="sending",
        )
        db.add(claim)
        db.commit()

        outgoing = OutgoingEmail(
            from_email=mailbox.from_email,
            from_name=mailbox.from_name or workspace.sender_name,
            to_email=email,
            subject=draft.subject,
            text_body=text,
            unsubscribe_url=compliance.unsubscribe_url(workspace.id, email),
        )
        try:
            message_id = sender.send(outgoing)
        except SendError as exc:
            if exc.kind == "recipient":
                claim.status, claim.error = "rejected", str(exc)
                db.commit()
                suppress_email(db, workspace.id, email, reason="hard_bounce")  # never try it again
                report.rejected += 1
                if _should_pause(db, mailbox):
                    mailbox.status = "paused"
                    mailbox.paused_reason = "too many rejected addresses; check list quality"
                    db.commit()
                    report.mailbox_paused = True
                    report.stopped_reason = "mailbox paused: too many rejected addresses"
                    break
                continue
            # config / transient: nothing was delivered, so release the claim and stop.
            db.delete(claim)
            db.commit()
            report.stopped_reason = f"{exc.kind}: {exc}"
            break

        claim.status, claim.message_id = "sent", message_id
        lead.status = "contacted"
        draft.status = "sent"
        db.commit()  # record immediately; a crash after this point cannot cause a re-send
        report.sent += 1

    report.quota_remaining = max(mailbox.daily_limit - count_today(db, mailbox.id), 0)
    return report
