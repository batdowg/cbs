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
from ..shared.sessions_lifecycle import (
    enforce_material_only_rules,
    is_material_only_session,
)
from ..services.materials_notifications import notify_materials_processors

ROW_FORMAT_CHOICES = ["Digital", "Physical", "Self-paced"]
CLIENT_RUN_BULK_ORDER = "Client-run Bulk order"
MATERIALS_OUTSTANDING_MESSAGE = "There are still material order items outstanding"
SIM_CREDITS_REF = "simulation_credits"

bp = Blueprint("materials", __name__, url_prefix="/sessions/<int:session_id>/materials")

ORDER_TYPES = [
    "KT-Run Standard materials",
    "KT-Run Modular materials",
    "KT-Run LDI materials",
    CLIENT_RUN_BULK_ORDER,
    "Simulation",
]

ORDER_STATUSES = [
    "New",
    "In progress",
    "Processed",
    "Finalized",
    "Ordered",
    "Shipped",
    "Delivered",
    "Cancelled",
    "On hold",
]


def is_client_run_bulk_order(order_type: str | None) -> bool:
    return (order_type or "").strip().lower() == CLIENT_RUN_BULK_ORDER.lower()


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


def _materials_shared_context(
    sess: Session,
    shipment: SessionShipping,
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
    session_locked = sess.status in {"Closed", "Cancelled"}
    readonly = view_only or session_locked
    can_manage = can_manage_shipment(current_user)
    can_edit_arrival = can_edit_materials_header(
        "arrival_date", current_user, shipment
    )
    fmt = shipment.materials_format or (
        "SIM_ONLY" if shipment.order_type == "Simulation" else ""
    )
    simulation_outlines = SimulationOutline.query.order_by(
        SimulationOutline.number, SimulationOutline.skill
    ).all()
    sim_base = bool(sess.workshop_type and sess.workshop_type.simulation_based)
    show_sim_outline = shipment.order_type == "Simulation" or sim_base
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
    return {
        "shipping_locations": shipping_locations,
        "readonly": readonly,
        "can_manage": can_manage,
        "can_edit_arrival": can_edit_arrival,
        "fmt": fmt,
        "simulation_outlines": simulation_outlines,
        "sim_base": sim_base,
        "show_sim_outline": show_sim_outline,
        "show_credits": show_credits,
        "language_options": language_options,
        "default_formats": default_formats,
    }


def _render_materials_response(
    sess: Session,
    shipment: SessionShipping,
    current_user: User | None,
    csa_view: bool,
    view_only: bool,
    form=None,
    errors=None,
    outline_error: bool = False,
    status_code: int = 200,
    shared_context: dict[str, object] | None = None,
):
    context = shared_context or _materials_shared_context(
        sess, shipment, current_user, csa_view, view_only
    )
    order_items = (
        MaterialOrderItem.query.filter_by(session_id=sess.id)
        .order_by(MaterialOrderItem.id)
        .all()
    )
    return (
        render_template(
            "sessions/materials.html",
            sess=sess,
            shipment=shipment,
            status=shipment.status,
            order_types=ORDER_TYPES,
            csa_view=csa_view,
            readonly=context["readonly"],
            current_user=current_user,
            can_edit_materials_header=can_edit_materials_header,
            can_manage=context["can_manage"],
            can_edit_arrival=context["can_edit_arrival"],
            can_mark_delivered=can_mark_delivered(current_user),
            shipping_locations=context["shipping_locations"],
            material_formats=material_format_choices(),
            language_options=context["language_options"],
            row_format_choices=ROW_FORMAT_CHOICES,
            default_formats=context["default_formats"],
            fmt=context["fmt"],
            show_sim_outline=context["show_sim_outline"],
            show_credits=context["show_credits"],
            sim_base=context["sim_base"],
            simulation_outlines=context["simulation_outlines"],
            form=form,
            errors=errors or {},
            outline_error=outline_error,
            order_items=order_items,
        ),
        status_code,
    )


def _sync_sim_credits(
    sess: Session, shipment: SessionShipping
) -> tuple[int, bool]:
    sim_base = bool(sess.workshop_type and sess.workshop_type.simulation_based)
    if not sim_base:
        return 0, False
    credits_val = max(shipment.credits or 0, 0)
    outline = sess.simulation_outline
    desired_title = f"SIM Credits ({outline.number})" if outline else None
    items = MaterialOrderItem.query.filter_by(session_id=sess.id).all()
    created = 0
    changed = False
    candidates: list[MaterialOrderItem] = []
    legacy: list[MaterialOrderItem] = []
    for item in items:
        title = (item.title_snapshot or "").strip()
        if item.catalog_ref == SIM_CREDITS_REF or (
            desired_title and title == desired_title
        ):
            candidates.append(item)
        elif title in {"Simulation Credits", "SIM Credits"}:
            legacy.append(item)
    target = candidates[0] if candidates else None
    extras = candidates[1:]
    if not target and legacy:
        target = legacy[0]
        extras.extend(legacy[1:])
    else:
        extras.extend(legacy)
    for extra in extras:
        db.session.delete(extra)
        changed = True
    if not desired_title or credits_val == 0:
        if target:
            db.session.delete(target)
            changed = True
        return 0, changed
    if not target:
        target = MaterialOrderItem(
            session_id=sess.id,
            catalog_ref=SIM_CREDITS_REF,
            title_snapshot=desired_title,
            language="en",
            format="Digital",
            quantity=credits_val,
            processed=False,
        )
        db.session.add(target)
        created = 1
        changed = True
    else:
        if target.catalog_ref != SIM_CREDITS_REF:
            target.catalog_ref = SIM_CREDITS_REF
            changed = True
    if target.title_snapshot != desired_title:
        target.title_snapshot = desired_title
        changed = True
    if target.language != "en":
        target.language = "en"
        changed = True
    if target.format != "Digital":
        target.format = "Digital"
        changed = True
    if target.quantity != credits_val:
        target.quantity = credits_val
        changed = True
    if target.description_snapshot:
        target.description_snapshot = None
        changed = True
    if target.sku_physical_snapshot:
        target.sku_physical_snapshot = None
        changed = True
    if target.processed:
        target.processed = False
        target.processed_at = None
        target.processed_by_id = None
        changed = True
    return created, changed


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


def _set_if_changed(obj, attr: str, value) -> bool:
    if getattr(obj, attr) != value:
        setattr(obj, attr, value)
        return True
    return False


@bp.route("", methods=["GET", "POST"])
@materials_access
def materials_view(
    session_id: int,
    sess: Session,
    current_user: User | None,
    csa_view: bool,
    view_only: bool,
):
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
            CLIENT_RUN_BULK_ORDER
            if is_material_only_session(sess)
            else "KT-Run Standard materials"
        )
        db.session.commit()
    if not shipment.material_sets:
        shipment.material_sets = sess.capacity or 0
        db.session.commit()
    shared_ctx = _materials_shared_context(
        sess, shipment, current_user, csa_view, view_only
    )
    readonly = shared_ctx["readonly"]
    can_manage = shared_ctx["can_manage"]
    can_edit_arrival = shared_ctx["can_edit_arrival"]
    fmt = shared_ctx["fmt"]
    simulation_outlines = shared_ctx["simulation_outlines"]
    sim_base = shared_ctx["sim_base"]
    show_sim_outline = shared_ctx["show_sim_outline"]
    show_credits = shared_ctx["show_credits"]
    if request.method == "POST":
        if readonly:
            abort(403)
        action = request.form.get("action")
        if not can_manage:
            abort(403)
        prior_notified = bool(sess.materials_notified_at)
        if action in {"update_header", "finalize"}:
            finalize = action == "finalize"
            ship_id = request.form.get("shipping_location_id")
            header_changed = False
            items_changed = False
            if ship_id is not None:
                new_ship_id = int(ship_id) if ship_id else None
                if sess.shipping_location_id != new_ship_id:
                    sess.shipping_location_id = new_ship_id
                    header_changed = True
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
                    header_changed |= _set_if_changed(
                        shipment, field, _parse_date(val)
                    )
                elif field == "materials_format":
                    header_changed |= _set_if_changed(shipment, field, val or None)
                elif field in {"material_sets", "credits"}:
                    try:
                        num_val = int(val) if val else 0
                    except ValueError:
                        num_val = 0
                    header_changed |= _set_if_changed(
                        shipment, field, max(0, num_val)
                    )
                else:
                    header_changed |= _set_if_changed(shipment, field, val or None)
            show_sim_outline = shipment.order_type == "Simulation" or sim_base
            show_credits = shipment.order_type == "Simulation" or sim_base
            errors: dict[str, str] = {}
            fmt = shipment.materials_format or (
                "SIM_ONLY" if shipment.order_type == "Simulation" else ""
            )
            if show_sim_outline:
                so_id = request.form.get("simulation_outline_id")
                new_so = int(so_id) if so_id else None
                if sess.simulation_outline_id != new_so:
                    sess.simulation_outline_id = new_so
                    header_changed = True
            if sim_base and not sess.simulation_outline_id:
                db.session.rollback()
                flash("Select a Simulation Outline to continue.", "error")
                context = _materials_shared_context(
                    sess, shipment, current_user, csa_view, view_only
                )
                return _render_materials_response(
                    sess,
                    shipment,
                    current_user,
                    csa_view,
                    view_only,
                    form=request.form,
                    errors=errors,
                    outline_error=True,
                    status_code=400,
                    shared_context=context,
                )
            header_changed |= _set_if_changed(
                shipment, "client_shipping_location_id", sess.shipping_location_id
            )
            if sess.shipping_location:
                header_changed |= _set_if_changed(
                    shipment, "contact_name", sess.shipping_location.contact_name
                )
                header_changed |= _set_if_changed(
                    shipment, "contact_phone", sess.shipping_location.contact_phone
                )
                header_changed |= _set_if_changed(
                    shipment, "contact_email", sess.shipping_location.contact_email
                )
                header_changed |= _set_if_changed(
                    shipment,
                    "address_line1",
                    sess.shipping_location.address_line1,
                )
                header_changed |= _set_if_changed(
                    shipment,
                    "address_line2",
                    sess.shipping_location.address_line2,
                )
                header_changed |= _set_if_changed(
                    shipment, "city", sess.shipping_location.city
                )
                header_changed |= _set_if_changed(
                    shipment, "state", sess.shipping_location.state
                )
                header_changed |= _set_if_changed(
                    shipment, "postal_code", sess.shipping_location.postal_code
                )
                header_changed |= _set_if_changed(
                    shipment, "country", sess.shipping_location.country
                )
            else:
                header_changed |= _set_if_changed(shipment, "contact_name", None)
                header_changed |= _set_if_changed(shipment, "contact_phone", None)
                header_changed |= _set_if_changed(shipment, "contact_email", None)
                header_changed |= _set_if_changed(shipment, "address_line1", None)
                header_changed |= _set_if_changed(shipment, "address_line2", None)
                header_changed |= _set_if_changed(shipment, "city", None)
                header_changed |= _set_if_changed(shipment, "state", None)
                header_changed |= _set_if_changed(shipment, "postal_code", None)
                header_changed |= _set_if_changed(shipment, "country", None)
            if original_order_type != shipment.order_type:
                if shipment.materials_option_id is not None:
                    shipment.materials_option_id = None
                    header_changed = True
                if shipment.materials_options:
                    shipment.materials_options = []
                    header_changed = True
            if shipment.order_type == "Simulation" and not shipment.materials_format:
                header_changed |= _set_if_changed(shipment, "materials_format", "SIM_ONLY")
            if errors:
                db.session.rollback()
                context = _materials_shared_context(
                    sess, shipment, current_user, csa_view, view_only
                )
                return _render_materials_response(
                    sess,
                    shipment,
                    current_user,
                    csa_view,
                    view_only,
                    form=request.form,
                    errors=errors,
                    status_code=400,
                    shared_context=context,
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
                processed_set = ("processed" in data) if finalize else True
                if fmt_val not in ROW_FORMAT_CHOICES:
                    fmt_val = ROW_FORMAT_CHOICES[0]
                if item_id and item_id in existing:
                    item = existing.pop(item_id)
                    if delete_flag or qty <= 0:
                        db.session.delete(item)
                        items_changed = True
                    else:
                        if item.quantity != qty:
                            item.quantity = qty
                            items_changed = True
                        if item.language != lang:
                            item.language = lang
                            items_changed = True
                        if item.format != fmt_val:
                            item.format = fmt_val
                            items_changed = True
                        if processed_set:
                            if processed_flag and not item.processed:
                                item.processed = True
                                item.processed_at = datetime.now(timezone.utc)
                                item.processed_by_id = (
                                    current_user.id if current_user else None
                                )
                                items_changed = True
                            elif not processed_flag and item.processed:
                                item.processed = False
                                item.processed_at = None
                                item.processed_by_id = None
                                items_changed = True
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
                    if dup.quantity != qty:
                        dup.quantity = qty
                        items_changed = True
                    if dup.language != lang:
                        dup.language = lang
                        items_changed = True
                    if dup.format != fmt_val:
                        dup.format = fmt_val
                        items_changed = True
                    if processed_set:
                        if processed_flag and not dup.processed:
                            dup.processed = True
                            dup.processed_at = datetime.now(timezone.utc)
                            dup.processed_by_id = (
                                current_user.id if current_user else None
                            )
                            items_changed = True
                        elif not processed_flag and dup.processed:
                            dup.processed = False
                            dup.processed_at = None
                            dup.processed_by_id = None
                            items_changed = True
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
                    processed=processed_flag if processed_set else False,
                )
                if processed_set and processed_flag:
                    item.processed_at = datetime.now(timezone.utc)
                    item.processed_by_id = current_user.id if current_user else None
                db.session.add(item)
                items_changed = True

            current_items = MaterialOrderItem.query.filter_by(
                session_id=sess.id
            ).all()
            all_processed = (
                all(i.processed for i in current_items)
                if current_items
                else True
            )
            has_items = bool(current_items)

            if not finalize and shipment.status != "Finalized":
                if (header_changed or items_changed) and (
                    not shipment.status
                    or shipment.status in {"New", "Processed"}
                ):
                    shipment.status = "In progress"
                db.session.flush()
                if all_processed and shipment.status != "Finalized":
                    if shipment.status != "Processed":
                        shipment.status = "Processed"
                elif not all_processed and shipment.status == "Processed":
                    shipment.status = "In progress"
                flash("Saved", "info")
            else:
                if not all_processed:
                    enforce_material_only_rules(sess)
                    db.session.commit()
                    flash(MATERIALS_OUTSTANDING_MESSAGE, "error")
                    return redirect(url_for("materials.materials_view", session_id=session_id))
                shipment.status = "Finalized"
                now = datetime.utcnow()
                if not sess.materials_ordered:
                    sess.materials_ordered = True
                    if not sess.materials_ordered_at:
                        sess.materials_ordered_at = now
                sess.ready_for_delivery = True
                if not sess.ready_at:
                    sess.ready_at = now
                if is_client_run_bulk_order(shipment.order_type):
                    sess.status = "Closed"
                flash("Materials order finalized", "success")

            enforce_material_only_rules(sess)
            should_notify = header_changed or items_changed or finalize
            db.session.commit()
            if should_notify:
                notify_materials_processors(
                    sess.id,
                    reason="updated" if prior_notified else "created",
                )
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
    return _render_materials_response(
        sess,
        shipment,
        current_user,
        csa_view,
        view_only,
        shared_context=shared_ctx,
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
    prior_notified = bool(sess.materials_notified_at)
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
    context = _materials_shared_context(
        sess, shipment, current_user, csa_view, view_only
    )
    if context["sim_base"] and not sess.simulation_outline_id:
        flash("Select a Simulation Outline to continue.", "error")
        return _render_materials_response(
            sess,
            shipment,
            current_user,
            csa_view,
            view_only,
            outline_error=True,
            status_code=400,
            shared_context=context,
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
                is_client_run_bulk_order(obj.order_type)
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
    new_credit_rows, credit_changed = _sync_sim_credits(sess, shipment)
    created += new_credit_rows
    notify_needed = created > 0 or credit_changed
    db.session.commit()
    if notify_needed:
        notify_materials_processors(
            sess.id, reason="updated" if prior_notified else "created"
        )
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
