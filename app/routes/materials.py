from __future__ import annotations

from datetime import date, datetime
from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session as flask_session, url_for

from ..app import db, User
from ..models import (
    Session,
    SessionShipping,
    SessionShippingItem,
    Material,
    MaterialsOption,
    ClientShippingLocation,
)

bp = Blueprint("materials", __name__, url_prefix="/sessions/<int:session_id>/materials")

ORDER_TYPES = [
    "KT-Run Standard materials",
    "KT-Run Modular materials",
    "KT-Run LDI materials",
    "Client-run Bulk order",
    "Simulation",
]

PHYSICAL_COMPONENT_CHOICES = [
    ("WORKSHOP_LEARNER", "Workshop Materials – Learner"),
    ("SESSION_MATERIALS", "Session Materials (wallcharts etc.)"),
    ("PROCESS_CARDS", "Physical Process Cards"),
    ("BOX_F", "Box F (markers, post-its etc.)"),
]

MATERIAL_FORMAT_CHOICES = [
    ("PHYSICAL", "All Physical"),
    ("DIGITAL", "All Digital"),
    ("MIXED", "Mixed"),
    ("SIM_ONLY", "SIM Only"),
]


def can_manage_shipment(user: User | None) -> bool:
    return bool(
        user
        and (
            user.is_app_admin or user.is_admin or getattr(user, "is_kcrm", False)
        )
    )


def can_mark_delivered(user: User | None) -> bool:
    return bool(user and (user.is_app_admin or user.is_admin))


def is_view_only(user: User | None) -> bool:
    return bool(
        user
        and (
            getattr(user, "is_kt_delivery", False)
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
            manageable = can_manage_shipment(user)
            vo = not manageable and is_view_only(user)
            if manageable or vo:
                return fn(
                    session_id,
                    *args,
                    **kwargs,
                    sess=sess,
                    current_user=user,
                    csa_view=False,
                    view_only=vo,
                )
        account_id = flask_session.get("participant_account_id")
        if account_id and sess.csa_account_id == account_id:
            return fn(
                session_id,
                *args,
                **kwargs,
                sess=sess,
                current_user=None,
                csa_view=True,
                view_only=True,
            )
        abort(403)

    return wrapper


CSA_FIELDS = {
    "arrival_date",
}


def can_edit_materials_header(
    field: str, user: User | None, shipment: SessionShipping | None
) -> bool:
    if can_manage_shipment(user):
        return True
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
def materials_view(
    session_id: int,
    sess: Session,
    current_user: User | None,
    csa_view: bool,
    view_only: bool,
):
    shipping_locations = (
        ClientShippingLocation.query.filter_by(
            client_id=sess.client_id, is_active=True
        )
        .order_by(ClientShippingLocation.id)
        .all()
        if sess.client_id
        else []
    )
    shipment = SessionShipping.query.filter_by(session_id=session_id).first()
    if not shipment:
        shipment = SessionShipping(
            session_id=session_id,
            created_by=current_user.id if current_user else None,
            name="Main Shipment",
        )
        db.session.add(shipment)
        db.session.commit()
    if sess.shipping_location:
        shipment.client_shipping_location_id = sess.shipping_location_id
        shipment.contact_name = sess.shipping_location.contact_name
        shipment.contact_phone = sess.shipping_location.contact_phone
        shipment.contact_email = sess.shipping_location.contact_email
        shipment.address_line1 = sess.shipping_location.address_line1
        shipment.address_line2 = sess.shipping_location.address_line2
        shipment.city = sess.shipping_location.city
        shipment.state = sess.shipping_location.state
        shipment.postal_code = sess.shipping_location.postal_code
        shipment.country = sess.shipping_location.country
    db.session.commit()
    readonly = view_only or sess.finalized or bool(shipment.delivered_at)
    if request.method == "POST":
        if readonly:
            abort(403)
        action = request.form.get("action")
        if action == "mark_delivered":
            if not can_mark_delivered(current_user):
                abort(403)
            shipment.delivered_at = datetime.utcnow()
            sess.materials_ordered = True
            sess.materials_ordered_at = datetime.utcnow()
            db.session.commit()
            flash("Shipment delivered", "info")
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if not can_manage_shipment(current_user):
            abort(403)
        if action == "update_header":
            ship_id = request.form.get("shipping_location_id")
            if ship_id is not None:
                sess.shipping_location_id = int(ship_id) if ship_id else None
            fields = CSA_FIELDS | {
                "courier",
                "tracking",
                "ship_date",
                "special_instructions",
                "order_type",
                "materials_option_id",
                "materials_format",
                "materials_po_number",
            }
            original_order_type = shipment.order_type
            for field in fields:
                val = request.form.get(field)
                if not can_edit_materials_header(field, current_user, shipment):
                    continue
                if field in {"ship_date", "arrival_date"}:
                    setattr(shipment, field, _parse_date(val))
                elif field == "materials_option_id":
                    setattr(shipment, field, int(val) if val else None)
                else:
                    setattr(shipment, field, val or None)
            errors: dict[str, str] = {}
            selected_components = request.form.getlist("components")
            required_components = shipment.materials_format in {"PHYSICAL", "MIXED"}
            if can_edit_materials_header("materials_components", current_user, shipment):
                if required_components and not selected_components:
                    errors["components"] = "Select physical components"
                    flash("Select physical components", "error")
                else:
                    shipment.materials_components = selected_components or None
            shipment.client_shipping_location_id = sess.shipping_location_id
            if sess.shipping_location:
                shipment.contact_name = sess.shipping_location.contact_name
                shipment.contact_phone = sess.shipping_location.contact_phone
                shipment.contact_email = sess.shipping_location.contact_email
                shipment.address_line1 = sess.shipping_location.address_line1
                shipment.address_line2 = sess.shipping_location.address_line2
                shipment.city = sess.shipping_location.city
                shipment.state = sess.shipping_location.state
                shipment.postal_code = sess.shipping_location.postal_code
                shipment.country = sess.shipping_location.country
            else:
                shipment.contact_name = None
                shipment.contact_phone = None
                shipment.contact_email = None
                shipment.address_line1 = None
                shipment.address_line2 = None
                shipment.city = None
                shipment.state = None
                shipment.postal_code = None
                shipment.country = None
            if original_order_type != shipment.order_type:
                shipment.materials_option_id = None
            if shipment.materials_format not in {"PHYSICAL", "MIXED"}:
                shipment.materials_components = None
            if errors:
                db.session.rollback()
                form = request.form.to_dict(flat=True)
                status = "Draft"
                if shipment.delivered_at:
                    status = "Delivered"
                elif shipment.ship_date:
                    status = "Shipped"
                materials = Material.query.order_by(Material.name).all() if not view_only else []
                materials_options = (
                    MaterialsOption.query.filter_by(order_type=shipment.order_type, is_active=True)
                    .order_by(MaterialsOption.title)
                    .all()
                    if shipment.order_type
                    else []
                )
                selected_option = (
                    db.session.get(MaterialsOption, shipment.materials_option_id)
                    if shipment.materials_option_id
                    else None
                )
                return (
                    render_template(
                        "sessions/materials.html",
                        sess=sess,
                        shipment=shipment,
                        status=status,
                        materials=materials,
                        materials_options=materials_options,
                        selected_option=selected_option,
                        order_types=ORDER_TYPES,
                        csa_view=csa_view,
                        readonly=readonly,
                        current_user=current_user,
                        can_edit_materials_header=can_edit_materials_header,
                        can_manage=can_manage_shipment(current_user),
                        can_mark_delivered=can_mark_delivered(current_user),
                        shipping_locations=shipping_locations,
                        material_formats=MATERIAL_FORMAT_CHOICES,
                        physical_components=PHYSICAL_COMPONENT_CHOICES,
                        required_components=required_components,
                        selected_components=selected_components,
                        form=form,
                        errors=errors,
                    ),
                    400,
                )
            if sess.client and not sess.client.sfc_link:
                sfc_link = request.form.get("sfc_link")
                if sfc_link:
                    sess.client.sfc_link = sfc_link
            db.session.commit()
            flash("Saved", "info")
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "add_item":
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
        if action == "update_item":
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
        if action == "delete_item":
            item_id = request.form.get("item_id")
            item = db.session.get(SessionShippingItem, int(item_id)) if item_id else None
            if item and item.session_shipping_id == shipment.id:
                db.session.delete(item)
                db.session.commit()
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "mark_shipped":
            if not shipment.ship_date:
                shipment.ship_date = date.today()
            db.session.commit()
            return redirect(url_for("materials.materials_view", session_id=session_id))
        if action == "delete":
            if shipment.delivered_at:
                flash("Cannot delete after delivery", "error")
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
    materials = Material.query.order_by(Material.name).all() if not view_only else []
    materials_options = (
        MaterialsOption.query.filter_by(order_type=shipment.order_type, is_active=True)
        .order_by(MaterialsOption.title)
        .all()
        if shipment.order_type
        else []
    )
    selected_option = (
        db.session.get(MaterialsOption, shipment.materials_option_id)
        if shipment.materials_option_id
        else None
    )
    return render_template(
        "sessions/materials.html",
        sess=sess,
        shipment=shipment,
        status=status,
        materials=materials,
        materials_options=materials_options,
        selected_option=selected_option,
        order_types=ORDER_TYPES,
        csa_view=csa_view,
        readonly=readonly,
        current_user=current_user,
        can_edit_materials_header=can_edit_materials_header,
        can_manage=can_manage_shipment(current_user),
        can_mark_delivered=can_mark_delivered(current_user),
        shipping_locations=shipping_locations,
        material_formats=MATERIAL_FORMAT_CHOICES,
        physical_components=PHYSICAL_COMPONENT_CHOICES,
        required_components=shipment.materials_format in {"PHYSICAL", "MIXED"},
        selected_components=shipment.materials_components or [],
        form=None,
        errors={},
    )


@bp.get("/options")
@materials_access
def options(session_id: int, sess: Session, current_user: User | None, csa_view: bool, view_only: bool):
    order_type = request.args.get("order_type")
    opts = []
    if order_type:
        opts = (
            MaterialsOption.query.filter_by(order_type=order_type, is_active=True)
            .order_by(MaterialsOption.title)
            .all()
        )
    return jsonify(options=[{"id": o.id, "title": o.title} for o in opts])
