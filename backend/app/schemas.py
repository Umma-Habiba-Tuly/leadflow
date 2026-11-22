from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    workspace_name: str = Field(min_length=1, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    niche: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    offer: Optional[str] = Field(
        default=None, max_length=1000, description="What you sell; used to score leads."
    )


class CampaignOut(CampaignIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    name: str
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    source: str
    status: str
    score: Optional[int] = None
    score_reason: Optional[str] = None


class ScoreIn(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)


class ScoreSummary(BaseModel):
    scored: int
    failed: int
    rate_limited: bool
    remaining: int
    last_error: Optional[str] = None  # why the most recent lead failed, if any


class ImportResult(BaseModel):
    added: int
    skipped_duplicates: int
    skipped_suppressed: int
    skipped_invalid: int


class SearchIn(BaseModel):
    max_results: int = Field(default=20, ge=1, le=60)


class EnrichIn(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)


class EnrichResult(BaseModel):
    checked: int
    found: int
    not_found: int
    suppressed: int


class SuppressionIn(BaseModel):
    email: EmailStr
    reason: str = "unsubscribed"


class SuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    reason: str


class LeadList(BaseModel):
    total: int
    items: List[LeadOut]


# ---------- sender profile, drafts ----------


class WorkspaceProfile(BaseModel):
    sender_name: Optional[str] = Field(default=None, max_length=200)
    company_name: Optional[str] = Field(default=None, max_length=200)
    postal_address: Optional[str] = Field(
        default=None, max_length=500, description="Required by CAN-SPAM on every commercial email."
    )


class WorkspaceProfileOut(WorkspaceProfile):
    complete: bool
    missing: List[str]


class DraftGenerateIn(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)
    min_score: int = Field(default=50, ge=0, le=100, description="Only draft for leads scoring at least this.")


class DraftGenerateSummary(BaseModel):
    generated: int
    failed: int
    rate_limited: bool
    remaining: int
    last_error: Optional[str] = None


class DraftPatch(BaseModel):
    subject: Optional[str] = Field(default=None, max_length=200)
    body: Optional[str] = Field(default=None, max_length=3000)
    approved: Optional[bool] = None


class DraftOut(BaseModel):
    id: int
    lead_id: int
    lead_name: str
    to_email: str
    subject: str
    body: str
    status: str
    preview: str  # exactly what would be sent: body + signature + footer


# ---------- mailboxes and sending ----------


def _no_control_chars(value: Optional[str]) -> Optional[str]:
    """Reject newlines etc. in anything that ends up in an email header (header injection)."""
    if value is not None and any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("must not contain control characters or line breaks")
    return value


class MailboxIn(BaseModel):
    from_email: EmailStr
    from_name: Optional[str] = Field(default=None, max_length=200)
    smtp_host: str = Field(min_length=1, max_length=255)
    smtp_port: int = Field(ge=1, le=65535)
    smtp_username: str = Field(min_length=1, max_length=320)
    smtp_password: str = Field(min_length=1, max_length=500, description="Write-only: stored encrypted, never returned.")
    security: Literal["starttls", "ssl", "none"] = "starttls"
    daily_limit: int = Field(default=30, ge=1, le=200)

    _clean_name = field_validator("from_name")(_no_control_chars)
    _clean_host = field_validator("smtp_host")(_no_control_chars)
    _clean_user = field_validator("smtp_username")(_no_control_chars)


class MailboxPatch(BaseModel):
    daily_limit: Optional[int] = Field(default=None, ge=1, le=200)
    status: Optional[Literal["active", "paused"]] = None
    smtp_password: Optional[str] = Field(default=None, min_length=1, max_length=500)


class MailboxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_email: str
    from_name: Optional[str] = None
    smtp_host: str
    smtp_port: int
    smtp_username: str
    security: str
    daily_limit: int
    status: str
    paused_reason: Optional[str] = None
    sent_today: int = 0  # no password field exists on this model, by design


class SendIn(BaseModel):
    mailbox_id: int
    limit: int = Field(default=10, ge=1, le=20)
    dry_run: bool = Field(default=True, description="Defaults to true: preview only. Set false to really send.")


class WouldSend(BaseModel):
    draft_id: int
    to_email: str
    subject: str


class SendSummary(BaseModel):
    dry_run: bool
    sent: int
    rejected: int
    skipped_opted_out: int
    quota_remaining: int
    mailbox_paused: bool
    stopped_reason: Optional[str] = None
    would_send: List[WouldSend] = []


class SentEmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    draft_id: int
    to_email: str
    subject: str
    status: str
    error: Optional[str] = None
    message_id: Optional[str] = None


# ---------- dashboard helpers ----------


class MeOut(BaseModel):
    email: str
    workspace_name: str
    profile_complete: bool
    profile_missing: List[str]


class CampaignStats(BaseModel):
    """Counts for a campaign's pipeline, including how many items are waiting for each next step."""

    leads: int
    with_email: int
    scored: int
    drafts: int
    approved: int
    sent: int
    opted_out: int
    # what the next button would act on:
    to_enrich: int
    to_score: int
    to_draft: int
    to_review: int  # drafts nobody has approved yet
    to_send: int  # approved drafts that can still go out (excludes refused or in-flight ones)
