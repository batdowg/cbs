from __future__ import annotations

from datetime import date, datetime
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
)

from ..app import db, User
from ..models import (
    Session,
    SessionShipping,
    SessionShippingItem,
    Material,
    MaterialsOption,
    ClientShippingLocation,
    SimulationOutline,
    AuditLog,
    WorkshopTypeMaterialDefault,
    MaterialOrderItem,
    SessionParticipant,
)
from ..shared.materials import (
    PHYSICAL_COMPONENTS,
    material_format_choices,
)

bp = Blueprint("materials", __name__, url_prefix="/sessions/<int:session_id>/materials")

ORDER_TYPES = [
    "KT-Run Standard materials",
    "KT-Run Modular materials",
    "KT-Run LDI materials",
    "Client-run Bulk order",
    "Simulation",
]

ORDER_STATUSES = [
    "New",
    "In progress",
    "Ordered",
    "Shipped",
    "Delivered",
    "Cancelled",
    "On hold",
]


def can_manage_shipment(user: User | None) -> bool:
    return bool(
        user and (user.is_app_admin or user.is_admin or getattr(user, "is_kcrm", False))
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
        ClientShippingLocation.query.filter_by(client_id=sess.client_id, is_active=True)
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
            order_date=date.today(),
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
    if shipment.order_type is None:
        shipment.order_type = (
            "Client-run Bulk order"
            if sess.materials_only
            else "KT-Run Standard materials"
        )
        db.session.commit()
    if (
        shipment.materials_option_id is None
        and sess.workshop_type
        and sess.workshop_type.default_materials_option_id
    ):
        shipment.materials_option_id = sess.workshop_type.default_materials_option_id
        if shipment.order_type == "KT-Run Modular materials":
            opt = db.session.get(MaterialsOption, shipment.materials_option_id)
            if opt:
                shipment.materials_options = [opt]
        db.session.commit()
    readonly = view_only or sess.finalized or bool(shipment.delivered_at)
    fmt = shipment.materials_format or (
        "SIM_ONLY" if shipment.order_type == "Simulation" else ""
    )
    selected_components = shipment.materials_components or []
    if fmt in {"ALL_DIGITAL", "SIM_ONLY"}:
        selected_components = []
    elif fmt == "ALL_PHYSICAL" and not selected_components:
        selected_components = [key for key, _ in PHYSICAL_COMPONENTS]
    components_required = fmt in {"ALL_PHYSICAL", "MIXED"}
    simulation_outlines = SimulationOutline.query.order_by(
        SimulationOutline.number, SimulationOutline.skill
    ).all()
    sim_base = bool(sess.workshop_type and sess.workshop_type.simulation_based)
    show_sim_outline = shipment.order_type == "Simulation" or sim_base
    status = shipment.status
    show_credits = shipment.order_type == "Simulation" or sim_base
    order_date_val = (
        shipment.order_date.isoformat()
        if shipment.order_date
        else date.today().isoformat()
    )
    if request.method == "POST":
        if readonly:
            abort(403)
        action = request.form.get("action")
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
                "order_date",
                "order_type",
                "materials_option_id",
                "materials_format",
                "materials_po_number",
                "material_sets",
                "credits",
                "status",
            }
            original_order_type = shipment.order_type
            original_status = shipment.status
            for field in fields:
                if (
                    field == "materials_option_id"
                    and shipment.order_type == "KT-Run Modular materials"
                ):
                    ids = [
                        int(v) for v in request.form.getlist("materials_option_id") if v
                    ]
                    shipment.materials_options = (
                        MaterialsOption.query.filter(MaterialsOption.id.in_(ids)).all()
                        if ids
                        else []
                    )
                    shipment.materials_option_id = ids[0] if ids else None
                    continue
                val = request.form.get(field)
                if not can_edit_materials_header(field, current_user, shipment):
                    continue
                if field in {"ship_date", "arrival_date", "order_date"}:
                    setattr(shipment, field, _parse_date(val))
                elif field == "materials_option_id":
                    shipment.materials_options = []
                    setattr(shipment, field, int(val) if val else None)
                elif field == "materials_format":
                    setattr(shipment, field, val or None)
                elif field in {"material_sets", "credits"}:
                    try:
                        num_val = int(val) if val else 0
                    except ValueError:
                        num_val = 0
                    setattr(shipment, field, max(0, num_val))
                elif field == "status":
                    if val:
                        setattr(shipment, field, val)
                else:
                    setattr(shipment, field, val or None)
            show_sim_outline = shipment.order_type == "Simulation" or sim_base
            show_credits = shipment.order_type == "Simulation" or sim_base
            errors: dict[str, str] = {}
            selected_components = request.form.getlist("components")
            fmt = shipment.materials_format or (
                "SIM_ONLY" if shipment.order_type == "Simulation" else ""
            )
            components_required = fmt in {"ALL_PHYSICAL", "MIXED"}
            if components_required:
                if not selected_components:
                    errors["components"] = "Select physical components"
                    flash("Select physical components", "error")
                else:
                    shipment.materials_components = selected_components
            else:
                shipment.materials_components = None
            if show_sim_outline:
                so_id = request.form.get("simulation_outline_id")
                sess.simulation_outline_id = int(so_id) if so_id else None
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
                shipment.materials_options = []
            if shipment.order_type == "Simulation" and not shipment.materials_format:
                shipment.materials_format = "SIM_ONLY"
            if original_status != shipment.status:
                if shipment.status == "Ordered":
                    sess.ready_for_delivery = True
                    sess.ready_at = datetime.utcnow()
                if shipment.status == "Delivered":
                    sess.status = "Finalized"
                    sess.finalized = True
                    sess.finalized_at = datetime.utcnow()
            if errors:
                db.session.rollback()
                form = request.form
                status = shipment.status
                materials = (
                    Material.query.order_by(Material.name).all()
                    if not view_only
                    else []
                )
                materials_options = (
                    MaterialsOption.query.filter_by(
                        order_type=shipment.order_type, is_active=True
                    )
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
                selected_options = shipment.materials_options
                return (
                    render_template(
                        "sessions/materials.html",
                        sess=sess,
                        shipment=shipment,
                        status=status,
                        materials=materials,
                        materials_options=materials_options,
                        selected_option=selected_option,
                        selected_options=selected_options,
                        order_types=ORDER_TYPES,
                        order_statuses=ORDER_STATUSES,
                        csa_view=csa_view,
                        readonly=readonly,
                        current_user=current_user,
                        can_edit_materials_header=can_edit_materials_header,
                        can_manage=can_manage_shipment(current_user),
                        can_mark_delivered=can_mark_delivered(current_user),
                        shipping_locations=shipping_locations,
                        material_formats=material_format_choices(),
                        physical_components=PHYSICAL_COMPONENTS,
                        components_required=components_required,
                        selected_components=selected_components,
                        fmt=fmt,
                        show_sim_outline=show_sim_outline,
                        show_credits=show_credits,
                        sim_base=sim_base,
                        order_date_val=order_date_val,
                        simulation_outlines=simulation_outlines,
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
            item = (
                db.session.get(SessionShippingItem, int(item_id)) if item_id else None
            )
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
            item = (
                db.session.get(SessionShippingItem, int(item_id)) if item_id else None
            )
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
    status = shipment.status
    materials = Material.query.order_by(Material.name).all() if not view_only else []
    order_items = (
        MaterialOrderItem.query.filter_by(session_id=session_id)
        .order_by(MaterialOrderItem.id)
        .all()
    )
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
    selected_options = shipment.materials_options
    return render_template(
        "sessions/materials.html",
        sess=sess,
        shipment=shipment,
        status=status,
        materials=materials,
        order_items=order_items,
        materials_options=materials_options,
        selected_option=selected_option,
        selected_options=selected_options,
        order_types=ORDER_TYPES,
        order_statuses=ORDER_STATUSES,
        csa_view=csa_view,
        readonly=readonly,
        current_user=current_user,
        can_edit_materials_header=can_edit_materials_header,
        can_manage=can_manage_shipment(current_user),
        can_mark_delivered=can_mark_delivered(current_user),
        shipping_locations=shipping_locations,
        material_formats=material_format_choices(),
        physical_components=PHYSICAL_COMPONENTS,
        components_required=components_required,
        selected_components=selected_components,
        fmt=fmt,
        show_sim_outline=show_sim_outline,
        show_credits=show_credits,
        sim_base=sim_base,
        order_date_val=order_date_val,
        simulation_outlines=simulation_outlines,
        form=None,
        errors={},
    )


@bp.post("/apply-defaults")
@materials_access
def apply_defaults(
    session_id: int,
    sess: Session,
    current_user: User | None,
    csa_view: bool,
    view_only: bool,
):
    if not can_manage_shipment(current_user) or view_only:
        abort(403)
    defaults = (
        WorkshopTypeMaterialDefault.query.filter_by(
            workshop_type_id=sess.workshop_type_id,
            delivery_type=sess.delivery_type,
            region_code=sess.region,
            language=sess.workshop_language,
            active=True,
        )
        .order_by(WorkshopTypeMaterialDefault.id)
        .all()
    )
    if not defaults:
        flash("No defaults found for this session's context.", "info")
        return redirect(
            url_for("materials.materials_view", session_id=session_id) + "#material-items"
        )

    participant_count = (
        db.session.query(db.func.count(SessionParticipant.id))
        .filter_by(session_id=sess.id)
        .scalar()
    )
    applied = 0
    skipped = 0
    for d in defaults:
        kind, _, ident = d.catalog_ref.partition(":")
        obj = None
        title = None
        desc = None
        sku = None
        fmt = d.default_format
        if kind == "materials_options" and ident.isdigit():
            obj = db.session.get(MaterialsOption, int(ident))
            if not obj:
                continue
            bulk = "bulk"
            if (
                obj.order_type == "Client-run Bulk order"
                or (obj.title and bulk in obj.title.lower())
                or (obj.description and bulk in obj.description.lower())
            ):
                continue
            title = obj.title
            desc = obj.description
            sku = obj.sku_physical
        elif kind in {"simulation_outline", "simulation_outlines"} and ident.isdigit():
            obj = db.session.get(SimulationOutline, int(ident))
            if not obj:
                continue
            title = obj.label
            fmt = "Digital"
        else:
            continue

        exists = MaterialOrderItem.query.filter_by(
            session_id=sess.id,
            catalog_ref=d.catalog_ref,
            language=d.language,
            format=fmt,
        ).first()
        if exists:
            skipped += 1
            continue
        item = MaterialOrderItem(
            session_id=sess.id,
            catalog_ref=d.catalog_ref,
            title_snapshot=title,
            description_snapshot=desc,
            sku_physical_snapshot=sku,
            language=d.language,
            format=fmt,
            quantity=participant_count or 0,
        )
        db.session.add(item)
        applied += 1
    db.session.commit()
    flash(f"Applied {applied} defaults ({skipped} skipped).", "info")
    return redirect(
        url_for("materials.materials_view", session_id=session_id) + "#material-items"
    )


@bp.post("/deliver")
@materials_access
def deliver(
    session_id: int,
    sess: Session,
    current_user: User | None,
    csa_view: bool,
    view_only: bool,
):
    if not can_mark_delivered(current_user):
        abort(403)
    if request.form.get("csrf_token") != flask_session.get("_csrf_token"):
        abort(400)
    shipment = SessionShipping.query.filter_by(session_id=session_id).first()
    if not shipment:
        abort(404)
    if shipment.status == "Delivered":
        flash("Already delivered", "error")
        return "", 403
    shipment.status = "Delivered"
    shipment.delivered_at = datetime.utcnow()
    db.session.add(
        AuditLog(
            user_id=current_user.id if current_user else None,
            session_id=sess.id,
            action="materials_delivered",
        )
    )
    db.session.commit()
    flash("Shipment marked delivered", "success")
    return redirect(url_for("materials.materials_view", session_id=session_id))


@bp.post("/undeliver")
@materials_access
def undeliver(
    session_id: int,
    sess: Session,
    current_user: User | None,
    csa_view: bool,
    view_only: bool,
):
    if not can_mark_delivered(current_user):
        abort(403)
    if request.form.get("csrf_token") != flask_session.get("_csrf_token"):
        abort(400)
    shipment = SessionShipping.query.filter_by(session_id=session_id).first()
    if not shipment:
        abort(404)
    shipment.status = "In progress"
    shipment.delivered_at = None
    db.session.add(
        AuditLog(
            user_id=current_user.id if current_user else None,
            session_id=sess.id,
            action="materials_undelivered",
        )
    )
    db.session.commit()
    flash("Shipment status set to In progress", "info")
    return redirect(url_for("materials.materials_view", session_id=session_id))


@bp.get("/options")
@materials_access
def options(
    session_id: int,
    sess: Session,
    current_user: User | None,
    csa_view: bool,
    view_only: bool,
):
    order_type = request.args.get("order_type")
    opts = []
    if order_type:
        opts = (
            MaterialsOption.query.filter_by(order_type=order_type, is_active=True)
            .order_by(MaterialsOption.title)
            .all()
        )
    return jsonify(options=[{"id": o.id, "title": o.title} for o in opts])
