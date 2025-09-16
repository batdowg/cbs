from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, redirect, render_template, request, session as flask_session, url_for

from ..app import db, User
from ..models import Session, SessionShipping, Client, WorkshopType
from .materials import ORDER_TYPES, ORDER_STATUSES, can_manage_shipment, is_view_only
from app.shared.materials import latest_arrival_date

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
    show_closed = request.args.get("closed") == "1"
    sort = request.args.get("sort", "arrival_date")
    direction = request.args.get("dir", "asc")

    query = (
        db.session.query(SessionShipping, Session, Client, WorkshopType)
        .join(Session, SessionShipping.session_id == Session.id)
        .outerjoin(Client, Session.client_id == Client.id)
        .outerjoin(WorkshopType, Session.workshop_type_id == WorkshopType.id)
    )

    if not show_closed:
        query = query.filter(Session.finalized.is_(False))
    query = query.filter(Session.cancelled.is_(False))

    if client_id:
        query = query.filter(Session.client_id == client_id)
    if order_type:
        query = query.filter(SessionShipping.order_type == order_type)
    if status:
        query = query.filter(SessionShipping.status == status)

    shipments = query.all()

    rows = []
    for sh, sess, client, wt in shipments:
        mstatus = sh.status
        rows.append(
            {
                "order_id": sh.id,
                "client": client.name if client else "",
                "title": sess.title,
                "workshop_type": wt.name if wt else "",
                "arrival_date": latest_arrival_date(sess),
                "order_type": sh.order_type or "",
                "materials_status": mstatus,
                "session_status": sess.computed_status,
                "session_id": sess.id,
            }
        )
    key_funcs = {
        "order_id": lambda r: r["order_id"],
        "client": lambda r: (r["client"] or "").lower(),
        "title": lambda r: (r["title"] or "").lower(),
        "workshop_type": lambda r: (r["workshop_type"] or "").lower(),
        "arrival_date": lambda r: r["arrival_date"] or date.min,
        "order_type": lambda r: (r["order_type"] or "").lower(),
        "materials_status": lambda r: r["materials_status"],
        "session_status": lambda r: r["session_status"],
    }
    reverse = direction == "desc"
    rows.sort(key=key_funcs.get(sort, key_funcs["arrival_date"]), reverse=reverse)

    clients = Client.query.order_by(Client.name).all()
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
        show_closed=show_closed,
    )
