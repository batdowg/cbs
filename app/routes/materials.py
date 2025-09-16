from __future__ import annotations

from datetime import date, datetime, timezone
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
    MaterialsOption,
    ClientShippingLocation,
    SimulationOutline,
    AuditLog,
    WorkshopTypeMaterialDefault,
    MaterialOrderItem,
)
from ..shared.materials import material_format_choices
from ..shared.languages import get_language_options

ROW_FORMAT_CHOICES = ["Digital", "Physical", "Self-paced"]

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


def compute_default_qty(sess: Session, shipment: SessionShipping | None) -> int:
    if shipment and shipment.material_sets:
        return shipment.material_sets
    return sess.capacity or 0


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
    if not shipment.material_sets:
        shipment.material_sets = sess.capacity or 0
        db.session.commit()
    readonly = view_only or bool(shipment.delivered_at)
    fmt = shipment.materials_format or (
        "SIM_ONLY" if shipment.order_type == "Simulation" else ""
    )
    simulation_outlines = SimulationOutline.query.order_by(
        SimulationOutline.number, SimulationOutline.skill
    ).all()
    sim_base = bool(sess.workshop_type and sess.workshop_type.simulation_based)
    show_sim_outline = shipment.order_type == "Simulation" or sim_base
    status = shipment.status
    show_credits = shipment.order_type == "Simulation" or sim_base
    language_options = get_language_options()
    default_formats: dict[int, str] = {}
    if sess.workshop_type_id:
        defs = WorkshopTypeMaterialDefault.query.filter_by(
            workshop_type_id=sess.workshop_type_id,
            delivery_type=sess.delivery_type,
            region_code=sess.region,
            language=sess.workshop_language,
            active=True,
        ).all()
        for d in defs:
            kind, _, ident = d.catalog_ref.partition(":")
            if kind == "materials_options" and ident.isdigit():
                default_formats[int(ident)] = d.default_format
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
                "materials_format",
                "material_sets",
                "credits",
            }
            original_order_type = shipment.order_type
            for field in fields:
                val = request.form.get(field)
                if not can_edit_materials_header(field, current_user, shipment):
                    continue
                if field in {"ship_date", "arrival_date", "order_date"}:
                    setattr(shipment, field, _parse_date(val))
                elif field == "materials_format":
                    setattr(shipment, field, val or None)
                elif field in {"material_sets", "credits"}:
                    try:
                        num_val = int(val) if val else 0
                    except ValueError:
                        num_val = 0
                    setattr(shipment, field, max(0, num_val))
                else:
                    setattr(shipment, field, val or None)
            show_sim_outline = shipment.order_type == "Simulation" or sim_base
            show_credits = shipment.order_type == "Simulation" or sim_base
            errors: dict[str, str] = {}
            fmt = shipment.materials_format or (
                "SIM_ONLY" if shipment.order_type == "Simulation" else ""
            )
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
            if errors:
                db.session.rollback()
                form = request.form
                return (
                    render_template(
                        "sessions/materials.html",
                        sess=sess,
                        shipment=shipment,
                        status=shipment.status,
                        order_types=ORDER_TYPES,
                        csa_view=csa_view,
                        readonly=readonly,
                        current_user=current_user,
                        can_edit_materials_header=can_edit_materials_header,
                        can_manage=can_manage_shipment(current_user),
                        can_mark_delivered=can_mark_delivered(current_user),
                        shipping_locations=shipping_locations,
                        material_formats=material_format_choices(),
                        language_options=language_options,
                        row_format_choices=ROW_FORMAT_CHOICES,
                        default_formats=default_formats,
                        fmt=fmt,
                        show_sim_outline=show_sim_outline,
                        show_credits=show_credits,
                        sim_base=sim_base,
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

            # process item rows
            from collections import defaultdict

            items_raw: dict[str, dict[str, str]] = defaultdict(dict)
            for key, val in request.form.items():
                if not key.startswith("items["):
                    continue
                try:
                    rest = key[6:]
                    row, field = rest.split("][")
                    field = field.rstrip("]")
                except ValueError:
                    continue
                items_raw[row][field] = val

            existing = {
                str(i.id): i
                for i in MaterialOrderItem.query.filter_by(session_id=sess.id).all()
            }

            for row, data in items_raw.items():
                item_id = data.get("id")
                delete_flag = data.get("delete") == "1"
                option_id = data.get("option_id")
                qty = int(data.get("quantity") or 0)
                lang = data.get("language") or sess.workshop_language
                fmt_val = data.get("format") or (shipment.materials_format or "Digital")
                processed_flag = data.get("processed") == "1"
                if fmt_val not in ROW_FORMAT_CHOICES:
                    fmt_val = ROW_FORMAT_CHOICES[0]
                if item_id and item_id in existing:
                    item = existing.pop(item_id)
                    if delete_flag or qty <= 0:
                        db.session.delete(item)
                    else:
                        item.quantity = qty
                        item.language = lang
                        item.format = fmt_val
                        if processed_flag and not item.processed:
                            item.processed = True
                            item.processed_at = datetime.now(timezone.utc)
                            item.processed_by_id = current_user.id if current_user else None
                        elif not processed_flag and item.processed:
                            item.processed = False
                            item.processed_at = None
                            item.processed_by_id = None
                    continue
                if delete_flag or not option_id:
                    continue
                opt = db.session.get(MaterialsOption, int(option_id))
                if not opt:
                    continue
                if qty <= 0:
                    qty = (
                        1
                        if opt.quantity_basis == "Per order"
                        else compute_default_qty(sess, shipment)
                    )
                dup = MaterialOrderItem.query.filter_by(
                    session_id=sess.id,
                    catalog_ref=f"materials_options:{opt.id}",
                    language=lang,
                    format=fmt_val,
                ).first()
                if dup:
                    dup.quantity = qty
                    dup.language = lang
                    dup.format = fmt_val
                    if processed_flag and not dup.processed:
                        dup.processed = True
                        dup.processed_at = datetime.now(timezone.utc)
                        dup.processed_by_id = current_user.id if current_user else None
                    elif not processed_flag and dup.processed:
                        dup.processed = False
                        dup.processed_at = None
                        dup.processed_by_id = None
                    continue
                item = MaterialOrderItem(
                    session_id=sess.id,
                    catalog_ref=f"materials_options:{opt.id}",
                    title_snapshot=opt.title,
                    description_snapshot=opt.description,
                    sku_physical_snapshot=opt.sku_physical,
                    language=lang,
                    format=fmt_val,
                    quantity=qty,
                    processed=processed_flag,
                )
                if processed_flag:
                    item.processed_at = datetime.now(timezone.utc)
                    item.processed_by_id = current_user.id if current_user else None
                db.session.add(item)

            db.session.commit()
            flash("Saved", "info")
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
    order_items = (
        MaterialOrderItem.query.filter_by(session_id=session_id)
        .order_by(MaterialOrderItem.id)
        .all()
    )
    return render_template(
        "sessions/materials.html",
        sess=sess,
        shipment=shipment,
        status=status,
        order_items=order_items,
        order_types=ORDER_TYPES,
        csa_view=csa_view,
        readonly=readonly,
        current_user=current_user,
        can_edit_materials_header=can_edit_materials_header,
        can_manage=can_manage_shipment(current_user),
        can_mark_delivered=can_mark_delivered(current_user),
        shipping_locations=shipping_locations,
        material_formats=material_format_choices(),
        language_options=language_options,
        row_format_choices=ROW_FORMAT_CHOICES,
        default_formats=default_formats,
        fmt=fmt,
        show_sim_outline=show_sim_outline,
        show_credits=show_credits,
        sim_base=sim_base,
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
    shipment = SessionShipping.query.filter_by(session_id=sess.id).first()
    if not shipment or shipment.material_sets <= 0:
        flash("Select # of Material sets first.", "error")
        return redirect(
            url_for("materials.materials_view", session_id=session_id)
            + "#material-items"
        )
    if shipment.order_type != "KT-Run Standard materials":
        flash("Defaults apply only to KT-Run Standard materials.", "error")
        return redirect(
            url_for("materials.materials_view", session_id=session_id)
            + "#material-items"
        )
    fmt_sel = request.form.get("materials_format")
    if fmt_sel is not None:
        shipment.materials_format = fmt_sel or None
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
        db.session.commit()
        return redirect(
            url_for("materials.materials_view", session_id=session_id)
            + "#material-items"
        )

    qty_base = compute_default_qty(sess, shipment)
    created = 0
    existing_refs = {
        i.catalog_ref
        for i in MaterialOrderItem.query.filter_by(session_id=sess.id).all()
    }
    for d in defaults:
        kind, _, ident = d.catalog_ref.partition(":")
        obj = None
        title = None
        desc = None
        sku = None
        fmt = d.default_format
        basis = "Per learner"
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
            basis = obj.quantity_basis
        elif kind in {"simulation_outline", "simulation_outlines"} and ident.isdigit():
            obj = db.session.get(SimulationOutline, int(ident))
            if not obj:
                continue
            title = obj.label
            fmt = "Digital"
        else:
            continue

        if d.catalog_ref in existing_refs:
            continue
        qty = qty_base if basis != "Per order" else 1
        item = MaterialOrderItem(
            session_id=sess.id,
            catalog_ref=d.catalog_ref,
            title_snapshot=title,
            description_snapshot=desc,
            sku_physical_snapshot=sku,
            language=d.language,
            format=fmt,
            quantity=qty,
        )
        db.session.add(item)
        created += 1
    db.session.commit()
    flash(f"Applied defaults: {created} added.", "success")
    return redirect(
        url_for("materials.materials_view", session_id=session_id) + "#material-items"
    )


@bp.post("/items/<int:item_id>/qty")
@materials_access
def update_order_item_quantity(
    session_id: int,
    item_id: int,
    sess: Session,
    current_user: User | None,
    csa_view: bool,
    view_only: bool,
):
    if not can_manage_shipment(current_user) or view_only:
        abort(403)
    item = MaterialOrderItem.query.filter_by(session_id=session_id, id=item_id).first()
    if not item:
        abort(404)
    data = request.get_json(silent=True) or request.form
    try:
        qty = int(data.get("quantity"))
    except (TypeError, ValueError):
        return "Invalid quantity", 400
    if qty < 0:
        qty = 0
    if qty == 0:
        db.session.delete(item)
    else:
        item.quantity = qty
    db.session.commit()
    return jsonify(status="ok", quantity=qty)


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
