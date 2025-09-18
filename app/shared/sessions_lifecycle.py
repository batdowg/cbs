"""Session lifecycle helpers."""

from __future__ import annotations

from typing import Any


def is_material_only_session(session: Any) -> bool:
    """Return True when the session represents a material-only engagement."""

    if session is None:
        return False
    delivery_type = getattr(session, "delivery_type", None)
    if isinstance(delivery_type, str) and delivery_type.strip().lower() == "material only":
        return True
    return bool(getattr(session, "materials_only", False))


def enforce_material_only_rules(session: Any) -> None:
    """Force invariants for material-only sessions."""

    if not is_material_only_session(session):
        return
    if getattr(session, "ready_for_delivery", False) or getattr(session, "finalized", False):
        session.status = "Closed"
    if getattr(session, "delivered", False):
        session.delivered = False
        if hasattr(session, "delivered_at"):
            session.delivered_at = None
