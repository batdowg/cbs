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
from ..models import Client, Session

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
