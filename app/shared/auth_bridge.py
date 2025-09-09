from __future__ import annotations

from datetime import datetime
from typing import Literal, Union

from flask import session

from ..app import db
from ..models import User, ParticipantAccount
from .passwords import check_password

def lookup_identity(email: str) -> Union[dict, None]:
    """Return account match info for email."""
    email_lc = (email or "").strip().lower()
    if not email_lc:
        return None
    user = User.query.filter(db.func.lower(User.email) == email_lc).first()
    participant = (
        ParticipantAccount.query.filter(db.func.lower(ParticipantAccount.email) == email_lc)
        .first()
    )
    if user and participant:
        return {"kind": "both", "user": user, "participant": participant}
    if user:
        return {"kind": "user", "obj": user}
    if participant:
        return {"kind": "participant", "obj": participant}
    return None


def verify_password(plain: str, hashed: str) -> bool:
    return check_password(plain, hashed)


def login_identity(identity: dict) -> None:
    """Populate session keys based on identity."""
    kind = identity.get("kind")
    obj = identity.get("obj") or identity.get("user")
    for key in ["user_id", "participant_account_id", "actor_kind", "user_email"]:
        session.pop(key, None)
    if kind in ["user", "both"] and obj is not None:
        session["user_id"] = obj.id
        session["user_email"] = obj.email
        session["actor_kind"] = "user"
    elif kind == "participant" and obj is not None:
        session["participant_account_id"] = obj.id
        session["user_email"] = obj.email
        session["actor_kind"] = "participant"
        obj.last_login = datetime.utcnow()
        db.session.commit()
