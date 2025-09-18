"""Session lifecycle helpers."""

from __future__ import annotations

from typing import Any, Iterable, Sequence


def is_material_only(session: Any) -> bool:
    """Return True when the session represents a material-only engagement."""

    if session is None:
        return False
    delivery_type = getattr(session, "delivery_type", None)
    if isinstance(delivery_type, str) and delivery_type.strip().lower() == "material only":
        return True
    return bool(getattr(session, "materials_only", False))


def is_material_only_session(session: Any) -> bool:
    """Backwards-compatible alias for older imports."""

    return is_material_only(session)


def _shipment_has_materials(shipment: Any) -> bool:
    if shipment is None:
        return False
    if getattr(shipment, "order_type", None):
        return True
    if getattr(shipment, "materials_option_id", None):
        return True
    if getattr(shipment, "materials_options", None):
        options: Sequence[Any] | None = getattr(shipment, "materials_options", None)
        if options:
            return True
    if getattr(shipment, "materials_format", None):
        return True
    if getattr(shipment, "materials_components", None):
        return True
    if getattr(shipment, "material_sets", 0):
        return True
    if getattr(shipment, "items", None):
        items: Sequence[Any] | None = getattr(shipment, "items", None)
        if items:
            return True
    return False


def has_materials(
    session: Any,
    *,
    shipment: Any | None = None,
    shipments: Iterable[Any] | None = None,
    order_items: Iterable[Any] | None = None,
) -> bool:
    """Return True when the session involves any materials activity."""

    if session is None:
        return False
    if is_material_only(session):
        return True
    if getattr(session, "no_material_order", False):
        return False
    if getattr(session, "materials_ordered", False):
        return True

    collection: Iterable[Any] | None = shipments
    if collection is None and shipment is not None:
        collection = [shipment]
    if collection:
        for sh in collection:
            if _shipment_has_materials(sh):
                return True

    if order_items:
        for _ in order_items:
            return True

    return False


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
