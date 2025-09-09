from __future__ import annotations

from datetime import date

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
    Client,
    ClientShippingLocation,
    MaterialsOption,
    SimulationOutline,
    Session,
    SessionShipping,
    WorkshopType,
)
from ..utils.languages import get_language_options
from ..utils.materials import PHYSICAL_COMPONENTS, material_format_choices
from ..utils.regions import get_region_options
from .materials import ORDER_TYPES

bp = Blueprint("materials_only", __name__)


def _parse_date(val: str | None):
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        return None


@bp.get("/materials-only/options")
def options():
    order_type = request.args.get("order_type")
    opts = []
    if order_type:
        opts = (
            MaterialsOption.query.filter_by(order_type=order_type, is_active=True)
            .order_by(MaterialsOption.title)
            .all()
        )
    return jsonify(options=[{"id": o.id, "title": o.title} for o in opts])

@bp.route("/materials-only", methods=["GET", "POST"])
def create():
    user_id = flask_session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))
    user = db.session.get(User, user_id)
    if not (user.is_app_admin or user.is_admin or getattr(user, "is_kcrm", False)):
        abort(403)
    if request.method == "POST":
        title = request.form.get("title")
        client_id = request.form.get("client_id", type=int)
        region = request.form.get("region")
        language = request.form.get("language")
        workshop_type_id = request.form.get("workshop_type_id", type=int)
        shipping_location_id = request.form.get("shipping_location_id", type=int)
        order_type = request.form.get("order_type") or "Client-run Bulk order"
        materials_option_ids = request.form.getlist("materials_option_id")
        material_format = request.form.get("materials_format") or None
        components = request.form.getlist("components")
        order_date = _parse_date(request.form.get("order_date")) or date.today()
        arrival_date = _parse_date(request.form.get("arrival_date"))
        ship_date = _parse_date(request.form.get("ship_date"))
        material_sets = request.form.get("material_sets", type=int)
        credits = request.form.get("credits", type=int)
        po_number = request.form.get("materials_po_number") or None
        sim_outline_id = request.form.get("simulation_outline_id", type=int)
        if not title or not client_id or not workshop_type_id:
            flash("Title, Client, and Workshop Type required", "error")
        else:
            sess = Session(
                title=title,
                client_id=client_id,
                region=region,
                workshop_language=language,
                workshop_type_id=workshop_type_id,
                simulation_outline_id=sim_outline_id,
                delivery_type="Material Order",
                start_date=date.today(),
                end_date=date.today(),
                materials_only=True,
                shipping_location_id=shipping_location_id,
            )
            db.session.add(sess)
            db.session.flush()
            shipment = SessionShipping(
                session_id=sess.id,
                order_type=order_type,
                status="New",
                credits=credits if credits is not None else 2,
                material_sets=material_sets if material_sets is not None else 0,
                materials_format=material_format
                or ("SIM_ONLY" if order_type == "Simulation" else None),
                materials_po_number=po_number,
                order_date=order_date,
                ship_date=ship_date,
                arrival_date=arrival_date,
            )
            if shipping_location_id:
                shipment.client_shipping_location_id = shipping_location_id
            if components:
                shipment.materials_components = components
            if materials_option_ids:
                if order_type == "KT-Run Modular materials":
                    opts = (
                        MaterialsOption.query.filter(
                            MaterialsOption.id.in_(materials_option_ids)
                        )
                        .order_by(MaterialsOption.id)
                        .all()
                    )
                    shipment.materials_options = opts
                else:
                    first_id = materials_option_ids[0]
                    shipment.materials_option_id = int(first_id) if first_id else None
            else:
                wt = db.session.get(WorkshopType, workshop_type_id)
                if wt and wt.default_materials_option_id:
                    if order_type == "KT-Run Modular materials":
                        opt = db.session.get(
                            MaterialsOption, wt.default_materials_option_id
                        )
                        if opt:
                            shipment.materials_options = [opt]
                    else:
                        shipment.materials_option_id = wt.default_materials_option_id
            db.session.add(shipment)
            db.session.commit()
            flash("Saved", "info")
            return redirect(url_for("materials_only.create"))
    clients = Client.query.order_by(Client.name).all()
    workshop_types = WorkshopType.query.order_by(WorkshopType.name).all()
    users = User.query.order_by(User.full_name).all()
    shipping_locations = (
        ClientShippingLocation.query.filter_by(is_active=True)
        .order_by(ClientShippingLocation.client_id)
        .all()
    )
    sim_outlines = SimulationOutline.query.order_by(
        SimulationOutline.number, SimulationOutline.skill
    ).all()
    return render_template(
        "materials_only.html",
        clients=clients,
        workshop_types=workshop_types,
        regions=get_region_options(),
        languages=get_language_options(),
        order_types=ORDER_TYPES,
        material_formats=material_format_choices(),
        physical_components=PHYSICAL_COMPONENTS,
        shipping_locations=shipping_locations,
        simulation_outlines=sim_outlines,
        today=date.today().isoformat(),
        users=users,
    )
