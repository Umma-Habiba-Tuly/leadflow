from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import Workspace
from app.db.session import get_db
from app.deps import Principal, get_principal
from app.schemas import WorkspaceProfile, WorkspaceProfileOut
from app.services.compliance import missing_profile_fields

router = APIRouter(prefix="/workspace", tags=["workspace"])


def _out(ws: Workspace) -> WorkspaceProfileOut:
    missing = missing_profile_fields(ws)
    return WorkspaceProfileOut(
        sender_name=ws.sender_name,
        company_name=ws.company_name,
        postal_address=ws.postal_address,
        complete=not missing,
        missing=missing,
    )


@router.get("/profile", response_model=WorkspaceProfileOut)
def get_profile(db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    return _out(db.get(Workspace, principal.workspace_id))


@router.put("/profile", response_model=WorkspaceProfileOut)
def update_profile(
    body: WorkspaceProfile, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)
):
    """Sender identity printed on every email. Must be complete before drafts can be generated."""
    ws = db.get(Workspace, principal.workspace_id)
    ws.sender_name = (body.sender_name or "").strip() or None
    ws.company_name = (body.company_name or "").strip() or None
    ws.postal_address = (body.postal_address or "").strip() or None
    db.commit()
    return _out(ws)
