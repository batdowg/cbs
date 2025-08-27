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

from ..app import db, User
from ..models import (
    Client,
    Session,
    ClientWorkshopLocation,
    ClientShippingLocation,
    ensure_virtual_workshop_locations,
)

bp = Blueprint("clients", __name__, url_prefix="/clients")


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
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name required", "error")
            return redirect(url_for("clients.new_client"))
        exists = (
            db.session.query(Client)
            .filter(db.func.lower(Client.name) == name.lower())
            .first()
        )
        if exists:
            flash("Client name must be unique", "error")
            return redirect(url_for("clients.new_client"))
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
        return redirect(url_for("clients.list_clients"))
    return render_template("clients/form.html", client=None, users=users)


@bp.route("/<int:client_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_client(client_id, current_user):
    client = db.session.get(Client, client_id)
    if not client:
        abort(404)
    users = User.query.order_by(User.email).all()
    if request.method == "POST":
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
        return redirect(url_for("clients.list_clients"))
    return render_template("clients/form.html", client=client, users=users)


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


@bp.post("/<int:client_id>/workshop-locations/inline")
@admin_required
def workshop_location_inline(client_id, current_user):
    client = db.session.get(Client, client_id)
    if not client:
        abort(404)
    label = request.form.get("label") or ""
    is_virtual = request.form.get("is_virtual", "1") not in {"0", "false", ""}
    platform = request.form.get("platform") or None
    loc = ClientWorkshopLocation(
        client_id=client_id,
        label=label,
        is_virtual=is_virtual,
        platform=platform,
        address_line1=request.form.get("address_line1") or None,
        address_line2=request.form.get("address_line2") or None,
        city=request.form.get("city") or None,
        state=request.form.get("state") or None,
        postal_code=request.form.get("postal_code") or None,
        country=request.form.get("country") or None,
    )
    db.session.add(loc)
    db.session.commit()
    return f"<option value='{loc.id}' selected>{loc.label}</option>"


@bp.post("/<int:client_id>/shipping-locations/inline")
@admin_required
def shipping_location_inline(client_id, current_user):
    client = db.session.get(Client, client_id)
    if not client:
        abort(404)
    loc = ClientShippingLocation(
        client_id=client_id,
        contact_name=request.form.get("contact_name") or None,
        contact_phone=request.form.get("contact_phone") or None,
        contact_email=request.form.get("contact_email") or None,
        address_line1=request.form.get("address_line1") or None,
        address_line2=request.form.get("address_line2") or None,
        city=request.form.get("city") or None,
        state=request.form.get("state") or None,
        postal_code=request.form.get("postal_code") or None,
        country=request.form.get("country") or None,
    )
    db.session.add(loc)
    db.session.commit()
    return (
        f"<option value='{loc.id}' selected>{loc.display_name()}</option>"
    )
