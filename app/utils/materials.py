from __future__ import annotations

from datetime import date

from ..app import db
from ..models import SessionShipping


def latest_arrival_date(sess) -> date | None:
    if not sess or not sess.id:
        return None
    return (
        db.session.query(db.func.max(SessionShipping.arrival_date))
        .filter(SessionShipping.session_id == sess.id)
        .scalar()
    )
