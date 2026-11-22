from typing import Callable, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import CryptoError, CryptoNotConfigured, decrypt_secret, encrypt_secret
from app.db.models import Lead, Mailbox, SentEmail, Workspace
from app.db.session import get_db
from app.deps import Principal, get_principal
from app.routers.campaigns import get_owned_campaign
from app.schemas import MailboxIn, MailboxOut, MailboxPatch, SendIn, SendSummary, SentEmailOut
from app.services import compliance, sending
from app.services.email_sender import EmailSender, SendError, SMTPSender
from app.services.netguard import hostname_is_public

router = APIRouter(tags=["sending"])

STANDARD_SMTP_PORTS = {25, 465, 587, 2525}

SenderFactory = Callable[[Mailbox], EmailSender]


def default_sender_factory(mailbox: Mailbox) -> EmailSender:
    try:
        password = decrypt_secret(mailbox.smtp_password_enc)
    except CryptoError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    return SMTPSender(mailbox.smtp_host, mailbox.smtp_port, mailbox.smtp_username, password, mailbox.security)


def get_sender_factory() -> SenderFactory:
    """FastAPI dependency. Tests replace it so no real SMTP connection is ever made."""
    return default_sender_factory


def _check_smtp_target(host: str, port: int, security: str) -> None:
    """The server will connect to this address on a client's behalf, so it must not be able to
    reach our own network (SSRF). Local servers are allowed only with ALLOW_PRIVATE_SMTP (dev)."""
    if settings.allow_private_smtp:
        return
    if security == "none":
        raise HTTPException(422, "Unencrypted SMTP is not allowed; use starttls or ssl")
    if port not in STANDARD_SMTP_PORTS:
        raise HTTPException(422, f"SMTP port must be one of {sorted(STANDARD_SMTP_PORTS)}")
    if not hostname_is_public(host, port):
        raise HTTPException(422, "SMTP host must be a public mail server")


def _owned_mailbox(db: Session, mailbox_id: int, principal: Principal) -> Mailbox:
    mailbox = db.scalar(
        select(Mailbox).where(Mailbox.id == mailbox_id, Mailbox.workspace_id == principal.workspace_id)
    )
    if mailbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mailbox not found")  # 404, never reveal other tenants' ids
    return mailbox


def _out(db: Session, mailbox: Mailbox) -> MailboxOut:
    out = MailboxOut.model_validate(mailbox)
    out.sent_today = sending.count_today(db, mailbox.id)
    return out


@router.post("/mailboxes", response_model=MailboxOut, status_code=status.HTTP_201_CREATED)
def add_mailbox(body: MailboxIn, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    _check_smtp_target(body.smtp_host, body.smtp_port, body.security)
    from_email = body.from_email.lower()
    if db.scalar(select(Mailbox).where(Mailbox.workspace_id == principal.workspace_id, Mailbox.from_email == from_email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This mailbox is already connected")
    try:
        encrypted = encrypt_secret(body.smtp_password)
    except CryptoNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    mailbox = Mailbox(
        workspace_id=principal.workspace_id, from_email=from_email, from_name=body.from_name,
        smtp_host=body.smtp_host, smtp_port=body.smtp_port, smtp_username=body.smtp_username,
        smtp_password_enc=encrypted, security=body.security, daily_limit=body.daily_limit,
    )
    db.add(mailbox)
    db.commit()
    return _out(db, mailbox)


@router.get("/mailboxes", response_model=List[MailboxOut])
def list_mailboxes(db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    rows = db.scalars(select(Mailbox).where(Mailbox.workspace_id == principal.workspace_id).order_by(Mailbox.id))
    return [_out(db, m) for m in rows]


@router.patch("/mailboxes/{mailbox_id}", response_model=MailboxOut)
def update_mailbox(
    mailbox_id: int, body: MailboxPatch, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)
):
    mailbox = _owned_mailbox(db, mailbox_id, principal)
    if body.daily_limit is not None:
        mailbox.daily_limit = body.daily_limit
    if body.status is not None:
        mailbox.status = body.status
        mailbox.paused_reason = None if body.status == "active" else (mailbox.paused_reason or "paused manually")
    if body.smtp_password is not None:
        try:
            mailbox.smtp_password_enc = encrypt_secret(body.smtp_password)
        except CryptoNotConfigured as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    db.commit()
    return _out(db, mailbox)


@router.post("/mailboxes/{mailbox_id}/check")
def check_mailbox(
    mailbox_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    make_sender: SenderFactory = Depends(get_sender_factory),
):
    """Connect and log in to the mailbox without sending anything."""
    mailbox = _owned_mailbox(db, mailbox_id, principal)
    _check_smtp_target(mailbox.smtp_host, mailbox.smtp_port, mailbox.security)
    try:
        make_sender(mailbox).check()
    except SendError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{exc.kind}: {exc}")
    return {"ok": True}


@router.post("/campaigns/{campaign_id}/send", response_model=SendSummary)
def send_campaign(
    campaign_id: int,
    body: SendIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    make_sender: SenderFactory = Depends(get_sender_factory),
):
    """Send approved drafts. DRY RUN BY DEFAULT: pass "dry_run": false to really send."""
    campaign = get_owned_campaign(db, campaign_id, principal)
    workspace = db.get(Workspace, principal.workspace_id)
    mailbox = _owned_mailbox(db, body.mailbox_id, principal)

    missing = compliance.missing_profile_fields(workspace)
    if missing:
        raise HTTPException(400, f"Complete your sender profile first (missing: {', '.join(missing)})")
    if mailbox.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mailbox is {mailbox.status}: {mailbox.paused_reason or 'reactivate it first'}")
    _check_smtp_target(mailbox.smtp_host, mailbox.smtp_port, mailbox.security)  # DNS can change; re-check

    sender = make_sender(mailbox)
    report = sending.send_batch(
        db, campaign=campaign, workspace=workspace, mailbox=mailbox, sender=sender,
        limit=body.limit, dry_run=body.dry_run,
    )
    return SendSummary(**report.__dict__)


@router.get("/campaigns/{campaign_id}/sent", response_model=List[SentEmailOut])
def list_sent(campaign_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    campaign = get_owned_campaign(db, campaign_id, principal)
    return list(
        db.scalars(
            select(SentEmail)
            .join(Lead, Lead.id == SentEmail.lead_id)
            .where(Lead.campaign_id == campaign.id, SentEmail.workspace_id == principal.workspace_id)
            .order_by(SentEmail.id)
        )
    )
