from __future__ import annotations

from datetime import date

from ..app import db
from ..models import SessionShipping


# Shared material-related choices
MATERIAL_FORMATS = ["ALL_PHYSICAL", "MIXED", "ALL_DIGITAL", "SIM_ONLY"]

MATERIAL_FORMAT_LABELS = {
    "ALL_PHYSICAL": "All Physical",
    "MIXED": "Mixed",
    "ALL_DIGITAL": "All Digital",
    "SIM_ONLY": "SIM Only",
}

PHYSICAL_COMPONENTS = [
    ("WORKSHOP_LEARNER", "Workshop Materials – Learner"),
    ("SESSION_MATERIALS", "Session Materials (wallcharts etc.)"),
    ("PROCESS_CARDS", "Physical Process Cards"),
    ("BOX_F", "Box F (markers, post-its etc.)"),
]


def material_format_choices() -> list[tuple[str, str]]:
    """Return material format options paired with labels."""
    return [(k, MATERIAL_FORMAT_LABELS[k]) for k in MATERIAL_FORMATS]


def latest_arrival_date(sess) -> date | None:
    if not sess or not sess.id:
        return None
    return (
        db.session.query(db.func.max(SessionShipping.arrival_date))
        .filter(SessionShipping.session_id == sess.id)
        .scalar()
    )
