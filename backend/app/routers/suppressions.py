from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Suppression
from app.db.session import get_db
from app.deps import Principal, get_principal
from app.schemas import SuppressionIn, SuppressionOut
from app.services.leads import suppress_email

router = APIRouter(prefix="/suppressions", tags=["compliance"])


@router.post("", response_model=SuppressionOut, status_code=status.HTTP_201_CREATED)
def add_suppression(
    body: SuppressionIn, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)
):
    """Add an email to the do-not-contact list and mark any existing leads with it."""
    return suppress_email(db, principal.workspace_id, body.email, body.reason)


@router.get("", response_model=List[SuppressionOut])
def list_suppressions(db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    return list(
        db.scalars(select(Suppression).where(Suppression.workspace_id == principal.workspace_id))
    )
