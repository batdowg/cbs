from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
)
from urllib.parse import urlparse

from ..app import db, User
from ..models import (
    Client,
    Session,
    ClientWorkshopLocation,
    ClientShippingLocation,
    ParticipantAccount,
    ensure_virtual_workshop_locations,
)

bp = Blueprint("clients", __name__, url_prefix="/clients")


def _safe_next(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc or not url.startswith("/"):
        return None
    return url


def client_edit_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        account_id = flask_session.get("participant_account_id")
        if user_id:
            user = db.session.get(User, user_id)
            if not user or not (user.is_app_admin or user.is_admin or user.is_kcrm):
                abort(403)
            return fn(*args, **kwargs, current_user=user, csa_account=None)
        if account_id:
            account = db.session.get(ParticipantAccount, account_id)
            if not account:
                abort(403)
            return fn(*args, **kwargs, current_user=None, csa_account=account)
        return redirect(url_for("auth.login"))

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login"))
        user = db.session.get(User, user_id)
        if not user or not (user.is_app_admin or user.is_admin):
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


@bp.get("/")
@admin_required
def list_clients(current_user):
    clients = Client.query.order_by(Client.name).all()
    return render_template("clients/list.html", clients=clients)


@bp.route("/new", methods=["GET", "POST"])
@admin_required
def new_client(current_user):
    users = User.query.order_by(User.email).all()
    next_url = _safe_next(request.values.get("next"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name required", "error")
            return redirect(url_for("clients.new_client", next=next_url))
        exists = (
            db.session.query(Client)
            .filter(db.func.lower(Client.name) == name.lower())
            .first()
        )
        if exists:
            flash("Client name must be unique", "error")
            return redirect(url_for("clients.new_client", next=next_url))
        client = Client(
            name=name,
            sfc_link=request.form.get("sfc_link") or None,
            crm_user_id=request.form.get("crm_user_id") or None,
            data_region=request.form.get("data_region") or None,
            status=request.form.get("status") or "active",
        )
        db.session.add(client)
        db.session.commit()
        ensure_virtual_workshop_locations(client.id)
        return redirect(next_url or url_for("clients.list_clients"))
    return render_template("clients/form.html", client=None, users=users, next_url=next_url)


@bp.route("/<int:client_id>/edit", methods=["GET", "POST"])
@client_edit_required
def edit_client(client_id, current_user, csa_account):
    client = db.session.get(Client, client_id)
    if not client:
        abort(404)
    section = request.values.get("section") or "workshop"
    loc_id = request.values.get("loc_id")
    next_url = _safe_next(request.values.get("next"))
    users = User.query.order_by(User.email).all()
    can_toggle = bool(current_user and (current_user.is_app_admin or current_user.is_admin or current_user.is_kcrm))
    if request.method == "POST":
        form = request.form.get("form")
        if form == "client":
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Name required", "error")
                return redirect(url_for("clients.edit_client", client_id=client_id))
            exists = (
                db.session.query(Client)
                .filter(db.func.lower(Client.name) == name.lower(), Client.id != client.id)
                .first()
            )
            if exists:
                flash("Client name must be unique", "error")
                return redirect(url_for("clients.edit_client", client_id=client_id))
            client.name = name
            client.sfc_link = request.form.get("sfc_link") or None
            client.crm_user_id = request.form.get("crm_user_id") or None
            client.data_region = request.form.get("data_region") or None
            client.status = request.form.get("status") or "active"
            db.session.commit()
            flash("Client saved", "success")
            redirect_url = next_url or url_for("clients.edit_client", client_id=client_id)
            return redirect(redirect_url)
        elif form == "workshop":
            if loc_id:
                loc = db.session.get(ClientWorkshopLocation, int(loc_id))
                if not loc or loc.client_id != client_id:
                    abort(404)
            else:
                loc = ClientWorkshopLocation(client_id=client_id)
            loc.label = (request.form.get("label") or "").strip()
            loc.is_virtual = request.form.get("is_virtual") in {"1", "on", "true"}
            loc.platform = request.form.get("platform") or None
            loc.access_notes = request.form.get("access_notes") or None
            loc.address_line1 = request.form.get("address_line1") or None
            loc.address_line2 = request.form.get("address_line2") or None
            loc.city = request.form.get("city") or None
            loc.state = request.form.get("state") or None
            loc.postal_code = request.form.get("postal_code") or None
            loc.country = request.form.get("country") or None
            if can_toggle and "is_active" in request.form:
                loc.is_active = request.form.get("is_active") in {"1", "on", "true"}
            db.session.add(loc)
            db.session.commit()
            flash("Workshop location saved", "success")
        elif form == "shipping":
            if loc_id:
                loc = db.session.get(ClientShippingLocation, int(loc_id))
                if not loc or loc.client_id != client_id:
                    abort(404)
            else:
                loc = ClientShippingLocation(client_id=client_id)
            loc.contact_name = request.form.get("contact_name") or None
            loc.contact_phone = request.form.get("contact_phone") or None
            loc.contact_email = request.form.get("contact_email") or None
            loc.address_line1 = request.form.get("address_line1") or None
            loc.address_line2 = request.form.get("address_line2") or None
            loc.city = request.form.get("city") or None
            loc.state = request.form.get("state") or None
            loc.postal_code = request.form.get("postal_code") or None
            loc.country = request.form.get("country") or None
            loc.notes = request.form.get("notes") or None
            if can_toggle and "is_active" in request.form:
                loc.is_active = request.form.get("is_active") in {"1", "on", "true"}
            db.session.add(loc)
            db.session.commit()
            flash("Shipping location saved", "success")
        elif form == "workshop_deactivate" and can_toggle:
            loc = db.session.get(ClientWorkshopLocation, int(loc_id))
            if loc and loc.client_id == client_id:
                loc.is_active = False
                db.session.commit()
                flash("Workshop location deactivated", "success")
        elif form == "shipping_deactivate" and can_toggle:
            loc = db.session.get(ClientShippingLocation, int(loc_id))
            if loc and loc.client_id == client_id:
                loc.is_active = False
                db.session.commit()
                flash("Shipping location deactivated", "success")
        redirect_url = next_url or url_for("clients.edit_client", client_id=client_id, section=section)
        if next_url:
            return redirect(redirect_url)
        return redirect(redirect_url)
    workshop_locations = (
        ClientWorkshopLocation.query.filter_by(client_id=client_id)
        .order_by(ClientWorkshopLocation.label)
        .all()
    )
    shipping_locations = (
        ClientShippingLocation.query.filter_by(client_id=client_id)
        .order_by(ClientShippingLocation.id)
        .all()
    )
    edit_wl = None
    edit_sl = None
    if section == "workshop" and loc_id:
        edit_wl = db.session.get(ClientWorkshopLocation, int(loc_id))
    if section == "shipping" and loc_id:
        edit_sl = db.session.get(ClientShippingLocation, int(loc_id))
    return render_template(
        "clients/edit.html",
        client=client,
        users=users,
        section=section,
        next_url=next_url,
        workshop_locations=workshop_locations,
        shipping_locations=shipping_locations,
        edit_wl=edit_wl,
        edit_sl=edit_sl,
        can_toggle=can_toggle,
    )


@bp.post("/<int:client_id>/delete")
@admin_required
def delete_client(client_id, current_user):
    client = db.session.get(Client, client_id)
    if not client:
        abort(404)
    if db.session.query(Session).filter_by(client_id=client_id).first():
        flash("Cannot delete client with sessions", "error")
        return redirect(url_for("clients.list_clients"))
    db.session.delete(client)
    db.session.commit()
    return redirect(url_for("clients.list_clients"))


@bp.post("/inline-new")
@admin_required
def inline_new_client(current_user):
    name = (request.form.get("name") or "").strip()
    if not name:
        return {"error": "Name required"}, 400
    exists = (
        db.session.query(Client)
        .filter(db.func.lower(Client.name) == name.lower())
        .first()
    )
    if exists:
        return {"error": "Client name must be unique"}, 400
    client = Client(name=name)
    db.session.add(client)
    db.session.commit()
    ensure_virtual_workshop_locations(client.id)
    return {"id": client.id, "name": client.name}


@bp.post("/<int:client_id>/inline-workshop-location")
@client_edit_required
def inline_workshop_location(client_id, current_user, csa_account):
    label = (request.form.get("label") or "").strip()
    if not label:
        return {"error": "Label required"}, 400
    loc = ClientWorkshopLocation(client_id=client_id, label=label)
    loc.is_virtual = request.form.get("is_virtual") in {"1", "on", "true"}
    loc.address_line1 = request.form.get("address_line1") or None
    loc.address_line2 = request.form.get("address_line2") or None
    loc.city = request.form.get("city") or None
    loc.state = request.form.get("state") or None
    loc.postal_code = request.form.get("postal_code") or None
    loc.country = request.form.get("country") or None
    db.session.add(loc)
    db.session.commit()
    return {"id": loc.id, "label": loc.label}


@bp.get("/<int:client_id>/inline-workshop-locations")
@client_edit_required
def list_inline_workshop_locations(client_id, current_user, csa_account):
    locs = (
        ClientWorkshopLocation.query.filter_by(client_id=client_id, is_active=True)
        .order_by(ClientWorkshopLocation.label)
        .all()
    )
    return {"locations": [{"id": l.id, "label": l.label} for l in locs]}


@bp.post("/<int:client_id>/inline-shipping-location")
@client_edit_required
def inline_shipping_location(client_id, current_user, csa_account):
    address_line1 = (request.form.get("address_line1") or "").strip()
    if not address_line1:
        return {"error": "Address required"}, 400
    loc = ClientShippingLocation(client_id=client_id)
    loc.contact_name = request.form.get("contact_name") or None
    loc.contact_phone = request.form.get("contact_phone") or None
    loc.contact_email = request.form.get("contact_email") or None
    loc.address_line1 = address_line1
    loc.address_line2 = request.form.get("address_line2") or None
    loc.city = request.form.get("city") or None
    loc.state = request.form.get("state") or None
    loc.postal_code = request.form.get("postal_code") or None
    loc.country = request.form.get("country") or None
    loc.notes = request.form.get("notes") or None
    db.session.add(loc)
    db.session.commit()
    return {"id": loc.id, "display": loc.display_name()}
