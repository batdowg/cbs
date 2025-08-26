from __future__ import annotations

from datetime import date, datetime
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session as flask_session, url_for

from ..app import db, User
from ..models import Session, SessionShipping, SessionShippingItem, Material

bp = Blueprint("materials", __name__, url_prefix="/sessions/<int:session_id>/materials")

ORDER_TYPES = [
    "KT-Run Standard materials",
    "KT-Run Modular materials",
    "KT-Run LDI materials",
    "Client-run Bulk order",
    "Simulation",
]


def _is_staff(user: User | None) -> bool:
    return bool(
        user
        and (
            user.is_app_admin
            or user.is_admin
            or getattr(user, "is_kcrm", False)
            or getattr(user, "is_kt_delivery", False)
            or getattr(user, "is_kt_staff", False)
            or getattr(user, "is_kt_contractor", False)
        )
    )


def materials_access(fn):
    @wraps(fn)
    def wrapper(session_id: int, *args, **kwargs):
        sess = db.session.get(Session, session_id)
        if not sess:
            abort(404)
        user = None
        user_id = flask_session.get("user_id")
        if user_id:
            user = db.session.get(User, user_id)
            if _is_staff(user):
                return fn(session_id, *args, **kwargs, sess=sess, current_user=user, csa_view=False)
        account_id = flask_session.get("participant_account_id")
        if account_id and sess.csa_account_id == account_id:
            return fn(session_id, *args, **kwargs, sess=sess, current_user=None, csa_view=True)
        abort(403)

    return wrapper


CSA_FIELDS = {
    "contact_name",
    "contact_phone",
    "contact_email",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "country",
    "arrival_date",
}


def can_edit_materials_header(field: str, user: User | None, shipment: SessionShipping | None) -> bool:
    if _is_staff(user):
        return True
    if shipment and shipment.submitted_at:
        return False
    return field in CSA_FIELDS


def _parse_date(val: str | None):
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        return None


@bp.route("", methods=["GET", "POST"])
@materials_access
def materials_view(session_id: int, sess: Session, current_user: User | None, csa_view: bool):
    shipment = SessionShipping.query.filter_by(session_id=session_id).first()
    readonly = False
    if not shipment:
        if not csa_view and current_user:
            shipment = SessionShipping(session_id=session_id, created_by=current_user.id)
            db.session.add(shipment)
            db.session.commit()
        else:
            flash("Materials order not initialized yet. A staff member will create it.", "info")
            readonly = True
            shipment = SessionShipping(session_id=session_id)
    if request.method == "POST":
        if readonly:
            abort(403)
        action = request.form.get("action")
        if action == "create":
            if csa_view:
                abort(403)
            if shipment:
                flash("Shipment already exists", "error")
            else:
                shipment = SessionShipping(session_id=session_id, created_by=current_user.id)
                db.session.add(shipment)
                db.session.commit()
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if not shipment:
            abort(404)
        if action == "update_header":
            unauthorized = False
            fields = CSA_FIELDS | {
                "courier",
                "tracking",
                "ship_date",
                "special_instructions",
                "order_type",
            }
            for field in fields:
                val = request.form.get(field)
                if not can_edit_materials_header(field, current_user, shipment):
                    if csa_view and val:
                        unauthorized = True
                    continue
                if field in {"ship_date", "arrival_date"}:
                    setattr(shipment, field, _parse_date(val))
                else:
                    setattr(shipment, field, val or None)
            if not csa_view and sess.client and not sess.client.sfc_link:
                sfc_link = request.form.get("sfc_link")
                if sfc_link:
                    sess.client.sfc_link = sfc_link
            db.session.commit()
            if unauthorized:
                flash("You can only provide shipping location details.", "error")
            else:
                flash("Saved", "info")
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "add_item" and not csa_view:
            material_id = request.form.get("material_id")
            qty = request.form.get("quantity")
            notes = request.form.get("notes")
            if material_id and qty and int(qty) >= 1:
                item = SessionShippingItem(
                    session_shipping_id=shipment.id,
                    material_id=int(material_id),
                    quantity=int(qty),
                    notes=notes,
                )
                db.session.add(item)
                db.session.commit()
            else:
                flash("Material and quantity required", "error")
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "update_item" and not csa_view:
            item_id = request.form.get("item_id")
            item = db.session.get(SessionShippingItem, int(item_id)) if item_id else None
            if item and item.session_shipping_id == shipment.id:
                material_id = request.form.get("material_id")
                qty = request.form.get("quantity")
                item.material_id = int(material_id) if material_id else None
                item.quantity = int(qty) if qty else 0
                item.notes = request.form.get("notes")
                db.session.commit()
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "delete_item" and not csa_view:
            item_id = request.form.get("item_id")
            item = db.session.get(SessionShippingItem, int(item_id)) if item_id else None
            if item and item.session_shipping_id == shipment.id:
                db.session.delete(item)
                db.session.commit()
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "submit" and not csa_view:
            if not shipment.arrival_date or len(shipment.items) == 0:
                flash("Arrival date and at least one line item required", "error")
            else:
                shipment.submitted_at = datetime.utcnow()
                db.session.commit()
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "mark_shipped" and not csa_view:
            if not shipment.ship_date:
                shipment.ship_date = date.today()
            db.session.commit()
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "mark_delivered" and not csa_view:
            shipment.delivered_at = datetime.utcnow()
            sess.materials_ordered = True
            sess.materials_ordered_at = datetime.utcnow()
            db.session.commit()
            flash("Shipment delivered", "info")
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "delete" and not csa_view:
            if shipment.submitted_at:
                flash("Cannot delete after submit", "error")
            else:
                db.session.delete(shipment)
                db.session.commit()
            return redirect(url_for("materials.materials_view", session_id=session_id))
    status = "Draft"
    if shipment:
        if shipment.delivered_at:
            status = "Delivered"
        elif shipment.ship_date:
            status = "Shipped"
        elif shipment.submitted_at:
            status = "Submitted"
    materials = Material.query.order_by(Material.name).all() if not csa_view else []
    return render_template(
        "sessions/materials.html",
        sess=sess,
        shipment=shipment,
        status=status,
        materials=materials,
        order_types=ORDER_TYPES,
        csa_view=csa_view,
        readonly=readonly,
        current_user=current_user,
        can_edit_materials_header=can_edit_materials_header,
    )
