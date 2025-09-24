from __future__ import annotations

import hashlib
import json
from typing import Iterable, Literal

from flask import current_app, render_template, url_for
from sqlalchemy.orm import joinedload

from .. import emailer
from ..app import db
from ..models import (
    MaterialOrderItem,
    ProcessorAssignment,
    Session,
    SessionShipping,
    User,
)
from ..shared.mail_utils import normalize_recipients
from ..shared.regions import code_to_label
from ..shared.time import now_utc

__all__ = [
    "materials_bucket_for",
    "resolve_processor_emails",
    "notify_materials_processors",
]


def materials_bucket_for(order: SessionShipping | None, session: Session | None) -> str:
    """Return the processing bucket for a materials order."""

    if order is None:
        return "Other"

    order_type = (order.order_type or "").strip().lower()
    if order_type == "simulation":
        return "Simulation"

    if session and session.workshop_type and session.workshop_type.simulation_based:
        return "Simulation"

    format_value = order.materials_format or ""
    format_label = str(format_value).strip().upper().replace("-", "_")
    format_label = format_label.replace(" ", "_")

    if format_label == "SIM_ONLY":
        return "Simulation"
    if format_label == "ALL_DIGITAL":
        return "Digital"
    if format_label in {"ALL_PHYSICAL", "MIXED"}:
        return "Physical"
    return "Other"


def _fetch_processor_emails(region: str, bucket: str) -> list[str]:
    rows = (
        ProcessorAssignment.query.join(User)
        .with_entities(User.email)
        .filter(
            ProcessorAssignment.region == region,
            ProcessorAssignment.processing_type == bucket,
        )
        .order_by(User.full_name, User.email)
        .all()
    )
    emails: list[str] = []
    for (email,) in rows:
        if not email:
            continue
        normalized = email.strip().lower()
        if normalized:
            emails.append(normalized)
    return emails


def resolve_processor_emails(region: str | None, bucket: str) -> list[str]:
    """Resolve processor emails using the configured fallback chain."""

    region_key = (region or "").strip() or "Other"
    bucket_key = bucket or "Other"
    candidates = [
        (region_key, bucket_key),
        (region_key, "Other"),
        ("Other", bucket_key),
        ("Other", "Other"),
    ]
    seen: set[str] = set()
    for region_candidate, bucket_candidate in candidates:
        emails = _fetch_processor_emails(region_candidate, bucket_candidate)
        resolved: list[str] = []
        for email in emails:
            if email not in seen:
                seen.add(email)
                resolved.append(email)
        if resolved:
            return resolved
    return []


def _serialize_items(items: Iterable[MaterialOrderItem]) -> list[dict]:
    payload: list[dict] = []
    for item in items:
        payload.append(
            {
                "catalog_ref": item.catalog_ref or "",
                "title": item.title_snapshot or "",
                "language": (item.language or "").lower(),
                "format": item.format or "",
                "quantity": int(item.quantity or 0),
            }
        )
    payload.sort(key=lambda row: (row["title"], row["language"], row["format"]))
    return payload


def _serialize_snapshot(session: Session, shipment: SessionShipping, items: list[MaterialOrderItem]) -> dict:
    session_dates = {
        "start_date": session.start_date.isoformat() if session.start_date else None,
        "end_date": session.end_date.isoformat() if session.end_date else None,
        "daily_start_time": session.daily_start_time.isoformat()
        if session.daily_start_time
        else None,
        "daily_end_time": session.daily_end_time.isoformat() if session.daily_end_time else None,
        "timezone": session.timezone or "",
    }
    shipping_snapshot = {
        "contact_name": shipment.contact_name or "",
        "contact_phone": shipment.contact_phone or "",
        "contact_email": shipment.contact_email or "",
        "address_line1": shipment.address_line1 or "",
        "address_line2": shipment.address_line2 or "",
        "city": shipment.city or "",
        "state": shipment.state or "",
        "postal_code": shipment.postal_code or "",
        "country": shipment.country or "",
    }
    workshop_location = session.workshop_location
    if workshop_location:
        workshop_snapshot = {
            "label": workshop_location.label or "",
            "address_line1": workshop_location.address_line1 or "",
            "address_line2": workshop_location.address_line2 or "",
            "city": workshop_location.city or "",
            "state": workshop_location.state or "",
            "postal_code": workshop_location.postal_code or "",
            "country": workshop_location.country or "",
        }
    else:
        workshop_snapshot = {
            "label": session.location or "",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "state": "",
            "postal_code": "",
            "country": "",
        }
    payload = {
        "session": {
            "delivery_type": session.delivery_type or "",
            "workshop_language": session.workshop_language or "",
        },
        "dates": session_dates,
        "shipping": shipping_snapshot,
        "workshop_location": workshop_snapshot,
        "order_header": {
            "order_type": shipment.order_type or "",
            "materials_format": shipment.materials_format or "",
            "material_sets": int(shipment.material_sets or 0),
            "special_instructions": shipment.special_instructions or "",
        },
        "items": _serialize_items(items),
    }
    return payload


def _compute_fingerprint(snapshot: dict) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def notify_materials_processors(
    session_id: int,
    *,
    reason: Literal["created", "updated"] | None = None,
) -> bool:
    """Send materials order email to processors when appropriate.

    Returns True when an email is sent.
    """

    session = (
        db.session.query(Session)
        .options(
            joinedload(Session.client),
            joinedload(Session.workshop_type),
            joinedload(Session.csa_account),
            joinedload(Session.workshop_location),
            joinedload(Session.shipping_location),
        )
        .filter(Session.id == session_id)
        .one_or_none()
    )
    if not session:
        return False

    delivery_type = (session.delivery_type or "").strip().lower()
    if delivery_type == "workshop only":
        return False

    shipment = (
        db.session.query(SessionShipping)
        .options(joinedload(SessionShipping.client_shipping_location))
        .filter(SessionShipping.session_id == session_id)
        .one_or_none()
    )
    if not shipment:
        return False

    items = (
        db.session.query(MaterialOrderItem)
        .filter(MaterialOrderItem.session_id == session_id)
        .all()
    )
    snapshot = _serialize_snapshot(session, shipment, items)
    fingerprint = _compute_fingerprint(snapshot)
    already_notified = bool(session.materials_notified_at)
    previous_fp = session.materials_order_fingerprint

    # Determine final reason after considering stored state.
    final_reason: Literal["created", "updated"]
    if already_notified:
        final_reason = "updated"
    else:
        final_reason = "created"
    if reason == "updated" and not already_notified:
        final_reason = "created"
    if reason == "created" and already_notified:
        final_reason = "updated"

    if final_reason == "updated" and previous_fp and previous_fp == fingerprint:
        return False
    if final_reason == "created" and previous_fp and previous_fp == fingerprint and already_notified:
        return False

    bucket = materials_bucket_for(shipment, session)
    recipients = resolve_processor_emails(session.region, bucket)
    normalized_recipients, recipient_header = normalize_recipients(recipients)
    if not normalized_recipients:
        current_app.logger.warning(
            "[MAIL-NO-RECIPIENTS] session=%s region=%s bucket=%s",
            session.id,
            session.region or "Other",
            bucket,
        )
        return False

    subject_reason = "NEW" if final_reason == "created" else "UPDATED"
    client_name = session.client.name if session.client else "Unknown client"
    workshop_code = (
        session.workshop_type.code
        if session.workshop_type and session.workshop_type.code
        else (session.code or "—")
    )
    subject = (
        f"[CBS] {subject_reason} Materials Order – {client_name} – {workshop_code} – Session #{session.id}"
    )
    items_sorted = sorted(
        items,
        key=lambda item: (
            item.title_snapshot or "",
            (item.language or "").lower(),
            item.format or "",
        ),
    )
    view_url = url_for("materials.materials_view", session_id=session.id, _external=True)
    region_label = code_to_label(session.region or "Other")
    html_body = render_template(
        "email/materials_processors_notification.html",
        session=session,
        shipment=shipment,
        items=items_sorted,
        reason=final_reason,
        snapshot=snapshot,
        view_url=view_url,
        processing_bucket=bucket,
        region_label=region_label,
    )
    text_body = render_template(
        "email/materials_processors_notification.txt",
        session=session,
        shipment=shipment,
        items=items_sorted,
        reason=final_reason,
        snapshot=snapshot,
        view_url=view_url,
        processing_bucket=bucket,
        region_label=region_label,
    )
    result = emailer.send(normalized_recipients, subject, text_body, html=html_body)
    if not result.get("ok"):
        current_app.logger.warning(
            "[MATERIALS-NOTIFY] Failed to send materials order email session=%s error=%s",
            session.id,
            result.get("detail"),
        )
        return False

    sent_at = now_utc()
    session.materials_notified_at = sent_at
    session.materials_order_fingerprint = fingerprint
    db.session.commit()
    current_app.logger.info(
        "[MATERIALS-NOTIFY] session=%s recipients=%s subject=\"%s\" reason=%s bucket=%s",
        session.id,
        recipient_header,
        subject,
        final_reason,
        bucket,
    )
    return True
