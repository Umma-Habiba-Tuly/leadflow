"""Everything legally required on outgoing email lives here, in code, never in an LLM prompt."""
from typing import List, Optional, Tuple

import jwt

from app.core.config import settings
from app.core.security import ALGORITHM
from app.db.models import Workspace


def missing_profile_fields(workspace: Workspace) -> List[str]:
    fields = {
        "sender_name": workspace.sender_name,
        "company_name": workspace.company_name,
        "postal_address": workspace.postal_address,
    }
    return [name for name, value in fields.items() if not (value or "").strip()]


# ---------- unsubscribe tokens ----------


def make_unsubscribe_token(workspace_id: int, email: str) -> str:
    """Signed, so nobody can forge an unsubscribe for someone else. Never expires:
    people click old emails and must still be able to opt out."""
    payload = {"typ": "unsub", "ws": workspace_id, "em": email.strip().lower()}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def read_unsubscribe_token(token: str) -> Optional[Tuple[int, str]]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    # "typ" stops a login token from being accepted here (and vice versa).
    if payload.get("typ") != "unsub":
        return None
    workspace_id, email = payload.get("ws"), payload.get("em")
    if not isinstance(workspace_id, int) or not isinstance(email, str) or not email:
        return None
    return workspace_id, email


def unsubscribe_url(workspace_id: int, email: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/u/{make_unsubscribe_token(workspace_id, email)}"


# ---------- final email text ----------


def compose_email_text(body: str, workspace: Workspace, unsub_url: str) -> str:
    """Body + signature + mandatory footer. Callers cannot skip the footer."""
    return (
        f"{body.strip()}\n\n"
        f"{workspace.sender_name}\n"
        f"{workspace.company_name}\n\n"
        "--\n"
        f"{workspace.company_name}, {workspace.postal_address}\n"
        f"Don't want these emails? Unsubscribe here: {unsub_url}\n"
    )
