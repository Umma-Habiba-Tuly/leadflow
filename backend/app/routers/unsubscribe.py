"""Public unsubscribe page (no login: recipients are not our users).

GET only shows a confirm button. POST actually unsubscribes. Email security scanners
and link previewers open links automatically; if GET unsubscribed, they'd opt people out
by accident. POST also matches the one-click standard (RFC 8058) mail clients use.
"""
import html

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.models import Workspace
from app.db.session import get_db
from app.services.compliance import read_unsubscribe_token
from app.services.leads import suppress_email

router = APIRouter(tags=["compliance"])

PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>{title}</title></head>"
    "<body style='font-family:system-ui,sans-serif;max-width:460px;margin:4rem auto;padding:0 1rem'>"
    "{inner}</body></html>"
)


def _page(title: str, inner: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(PAGE.format(title=html.escape(title), inner=inner), status_code=status_code)


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _invalid() -> HTMLResponse:
    return _page("Invalid link", "<h2>This link isn't valid</h2><p>It may have been copied incorrectly.</p>", 400)


@router.get("/u/{token}", response_class=HTMLResponse)
def confirm_page(token: str, db: Session = Depends(get_db)):
    parsed = read_unsubscribe_token(token)
    if parsed is None or db.get(Workspace, parsed[0]) is None:
        return _invalid()
    _, email = parsed
    return _page(
        "Unsubscribe",
        f"<h2>Unsubscribe</h2><p>Stop all emails to <b>{html.escape(_mask(email))}</b>?</p>"
        "<form method='post'><button type='submit' style='padding:.6rem 1.2rem;font-size:1rem'>"
        "Yes, unsubscribe me</button></form>",
    )


@router.post("/u/{token}", response_class=HTMLResponse)
def do_unsubscribe(token: str, db: Session = Depends(get_db)):
    parsed = read_unsubscribe_token(token)
    if parsed is None or db.get(Workspace, parsed[0]) is None:
        return _invalid()
    workspace_id, email = parsed
    suppress_email(db, workspace_id, email, reason="unsubscribed")
    return _page(
        "Unsubscribed",
        f"<h2>You're unsubscribed</h2><p>{html.escape(_mask(email))} won't receive any more emails from us.</p>",
    )
