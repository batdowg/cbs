from __future__ import annotations

from datetime import date, datetime

from flask import Blueprint, abort, redirect, render_template, request, session as flask_session, url_for
from sqlalchemy import func, or_
from sqlalchemy.orm import aliased, joinedload, selectinload

from ..app import db, User
from ..models import (
    Session,
    SessionParticipant,
    SessionShipping,
    Client,
    WorkshopType,
    SimulationOutline,
    ClientShippingLocation,
    MaterialOrderItem,
    Participant,
)
from .materials import ORDER_TYPES, ORDER_STATUSES, can_manage_shipment, is_view_only

bp = Blueprint("materials_orders", __name__, url_prefix="/materials")


@bp.route("")
def list_orders():
    user_id = flask_session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))
    user = db.session.get(User, user_id)
    if not (can_manage_shipment(user) or is_view_only(user)):
        abort(403)
    client_id = request.args.get("client_id", type=int)
    order_type = request.args.get("order_type")
    status = request.args.get("status")
    workshop_status_arg = request.args.get("workshop_status")
    closed_flag = request.args.get("closed")
    if workshop_status_arg is None and closed_flag is not None:
        workshop_status_arg = "all" if closed_flag == "1" else "not_closed"
    if workshop_status_arg is None:
        workshop_status_filter = "not_closed"
        workshop_status_param = None
    else:
        normalized = workshop_status_arg.strip()
        lower = normalized.lower()
        compact = lower.replace(" ", "_")
        if not normalized or lower == "all":
            workshop_status_filter = "all"
            workshop_status_param = "all"
        elif compact in {"not_closed", "not-closed"}:
            workshop_status_filter = "not_closed"
            workshop_status_param = "not_closed"
        elif lower == "closed":
            workshop_status_filter = "Closed"
            workshop_status_param = "Closed"
        else:
            workshop_status_filter = normalized
            workshop_status_param = normalized
    sort = request.args.get("sort", "arrival_date")
    direction = request.args.get("dir", "asc")

    latest_processed_sq = (
        db.session.query(
            MaterialOrderItem.session_id.label("session_id"),
            MaterialOrderItem.format.label("format"),
            MaterialOrderItem.processed_at.label("processed_at"),
            MaterialOrderItem.processed_by_id.label("processed_by_id"),
            func.row_number()
            .over(
                partition_by=(
                    MaterialOrderItem.session_id,
                    MaterialOrderItem.format,
                ),
                order_by=MaterialOrderItem.processed_at.desc().nulls_last(),
            )
            .label("rank"),
        )
        .filter(
            MaterialOrderItem.processed.is_(True),
            MaterialOrderItem.processed_at.isnot(None),
        )
        .subquery()
    )
    digital_latest = aliased(latest_processed_sq)
    physical_latest = aliased(latest_processed_sq)
    digital_user = aliased(User)
    physical_user = aliased(User)

    query = (
        db.session.query(
            SessionShipping,
            Session,
            Client,
            WorkshopType,
            SimulationOutline,
            ClientShippingLocation,
            digital_latest.c.processed_at.label("digital_processed_at"),
            digital_user.full_name.label("digital_processor_name"),
            digital_user.email.label("digital_processor_email"),
            physical_latest.c.processed_at.label("physical_processed_at"),
            physical_user.full_name.label("physical_processor_name"),
            physical_user.email.label("physical_processor_email"),
        )
        .join(Session, SessionShipping.session_id == Session.id)
        .outerjoin(Client, Session.client_id == Client.id)
        .outerjoin(WorkshopType, Session.workshop_type_id == WorkshopType.id)
        .outerjoin(SimulationOutline, Session.simulation_outline_id == SimulationOutline.id)
        .outerjoin(
            ClientShippingLocation,
            Session.shipping_location_id == ClientShippingLocation.id,
        )
        .outerjoin(
            digital_latest,
            (digital_latest.c.session_id == Session.id)
            & (digital_latest.c.format == "Digital")
            & (digital_latest.c.rank == 1),
        )
        .outerjoin(digital_user, digital_user.id == digital_latest.c.processed_by_id)
        .outerjoin(
            physical_latest,
            (physical_latest.c.session_id == Session.id)
            & (physical_latest.c.format == "Physical")
            & (physical_latest.c.rank == 1),
        )
        .outerjoin(physical_user, physical_user.id == physical_latest.c.processed_by_id)
        .options(
            joinedload(Session.lead_facilitator),
            selectinload(Session.facilitators),
        )
    )

    if workshop_status_filter == "not_closed":
        query = query.filter(or_(Session.status.is_(None), Session.status != "Closed"))
    elif workshop_status_filter == "Closed":
        query = query.filter(Session.status == "Closed")
    query = query.filter(Session.cancelled.is_(False))

    if client_id:
        query = query.filter(Session.client_id == client_id)
    if order_type:
        query = query.filter(SessionShipping.order_type == order_type)
    if status:
        query = query.filter(SessionShipping.status == status)

    shipments = query.all()

    session_ids = [sess.id for (_, sess, *_rest) in shipments]
    participant_map: dict[int, list[str]] = {}
    if session_ids:
        participant_rows = (
            db.session.query(
                SessionParticipant.session_id,
                Participant.full_name,
                Participant.email,
            )
            .join(Participant, Participant.id == SessionParticipant.participant_id)
            .filter(SessionParticipant.session_id.in_(session_ids))
            .order_by(Participant.full_name.asc(), Participant.email.asc())
            .all()
        )
        for sid, full_name, email in participant_rows:
            display = (full_name or "").strip() or (email or "").strip()
            if not display:
                continue
            participant_map.setdefault(sid, []).append(display)

    def format_processed(ts, name, email):
        if not ts:
            return ""
        label = ts.strftime("%Y-%m-%d %H:%M") + " UTC"
        display = (name or "").strip() or (email or "").strip()
        if display:
            label += f" {display}"
        return label

    def shipping_title_for(loc, client):
        if not loc:
            return ""
        if loc.title:
            return loc.title
        pieces: list[str] = []
        if client and client.name:
            pieces.append(client.name)
        if loc.city:
            pieces.append(loc.city)
        elif loc.address_line1:
            pieces.append(loc.address_line1)
        elif loc.contact_name:
            pieces.append(loc.contact_name)
        if not pieces:
            return loc.display_name()
        return " / ".join(pieces[:2])

    rows = []
    for (
        shipment,
        sess,
        client,
        workshop,
        outline,
        ship_loc,
        digital_processed_at,
        digital_processor_name,
        digital_processor_email,
        physical_processed_at,
        physical_processor_name,
        physical_processor_email,
    ) in shipments:
        facilitator_names: list[str] = []
        seen_ids: set[int] = set()
        if sess.lead_facilitator and sess.lead_facilitator.id:
            seen_ids.add(sess.lead_facilitator.id)
            leader_display = (
                (sess.lead_facilitator.full_name or "").strip()
                or (sess.lead_facilitator.email or "").strip()
            )
            if leader_display:
                facilitator_names.append(leader_display)
        sorted_facilitators = sorted(
            sess.facilitators,
            key=lambda u: ((u.full_name or u.email or "").lower()),
        )
        for fac in sorted_facilitators:
            if not fac or not fac.id or fac.id in seen_ids:
                continue
            seen_ids.add(fac.id)
            display = (fac.full_name or "").strip() or (fac.email or "").strip()
            if display:
                facilitator_names.append(display)

        learners = participant_map.get(sess.id, [])
        outline_label = ""
        if outline:
            outline_label = f"{outline.number} — {outline.skill} — {outline.descriptor}"
            if getattr(outline, "level", None):
                outline_label += f" ({outline.level})"

        workshop_code = ""
        workshop_name = ""
        if workshop:
            workshop_code = workshop.code or ""
            workshop_name = workshop.name or ""
        else:
            workshop_code = sess.code or ""

        bulk_receiver_email = ""
        if ship_loc and ship_loc.contact_email:
            bulk_receiver_email = ship_loc.contact_email
        elif shipment.contact_email:
            bulk_receiver_email = shipment.contact_email

        rows.append(
            {
                "order_id": shipment.id,
                "session_id": sess.id,
                "title": sess.title or "",
                "status": shipment.status or "",
                "start_date": sess.start_date,
                "client": client.name if client else "",
                "order_type": shipment.order_type or "",
                "workshop_code": workshop_code,
                "workshop_name": workshop_name,
                "processed_digital_at": digital_processed_at,
                "processed_digital_display": format_processed(
                    digital_processed_at,
                    digital_processor_name,
                    digital_processor_email,
                ),
                "processed_physical_at": physical_processed_at,
                "processed_physical_display": format_processed(
                    physical_processed_at,
                    physical_processor_name,
                    physical_processor_email,
                ),
                "arrival_date": shipment.arrival_date,
                "bulk_receiver": bulk_receiver_email,
                "outline": outline_label,
                "has_outline": bool(sess.simulation_outline_id),
                "credits": shipment.credits,
                "teams": (shipment.credits * 2) if shipment.credits is not None else None,
                "facilitators": facilitator_names,
                "learners": learners,
                "region": sess.region or "",
                "shipping_title": shipping_title_for(ship_loc, client),
                "workshop_status": sess.computed_status,
            }
        )

    reverse = direction == "desc"

    def credits_sort_key(row):
        value = row["credits"]
        if (not row.get("has_outline")) or value is None:
            return float("-inf") if reverse else float("inf")
        return value

    key_funcs = {
        "order_id": lambda r: r["order_id"],
        "title": lambda r: (r["title"] or "").lower(),
        "status": lambda r: (r["status"] or "").lower(),
        "materials_status": lambda r: (r["status"] or "").lower(),
        "start_date": lambda r: r["start_date"] or date.min,
        "client": lambda r: (r["client"] or "").lower(),
        "order_type": lambda r: (r["order_type"] or "").lower(),
        "workshop_code": lambda r: (r["workshop_code"] or "").lower(),
        "processed_digital": lambda r: r["processed_digital_at"] or datetime.min,
        "processed_physical": lambda r: r["processed_physical_at"] or datetime.min,
        "arrival_date": lambda r: r["arrival_date"] or date.min,
        "bulk_receiver": lambda r: (r["bulk_receiver"] or "").lower(),
        "outline": lambda r: (r["outline"] or "").lower(),
        "teams": credits_sort_key,
        "region": lambda r: (r["region"] or "").lower(),
        "shipping_title": lambda r: (r["shipping_title"] or "").lower(),
        "workshop_status": lambda r: (r["workshop_status"] or "").lower(),
        "session_status": lambda r: (r["workshop_status"] or "").lower(),
    }
    rows.sort(key=key_funcs.get(sort, key_funcs["arrival_date"]), reverse=reverse)

    clients = Client.query.order_by(Client.name).all()

    if workshop_status_filter == "not_closed":
        workshop_status_chip_label = "Status: not Closed"
    elif workshop_status_filter in {"all", None}:
        workshop_status_chip_label = None
    else:
        workshop_status_chip_label = f"Status: {workshop_status_filter}"
    return render_template(
        "materials_orders.html",
        rows=rows,
        clients=clients,
        order_types=ORDER_TYPES,
        statuses=ORDER_STATUSES,
        client_id=client_id,
        order_type=order_type,
        status=status,
        sort=sort,
        dir=direction,
        workshop_status_filter=workshop_status_filter,
        workshop_status_param=workshop_status_param,
        workshop_status_chip_label=workshop_status_chip_label,
    )
