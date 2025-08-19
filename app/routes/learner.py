from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    send_file,
    session as flask_session,
    url_for,
)

from ..app import db, User
from ..models import Certificate

bp = Blueprint("learner", __name__)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in flask_session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


@bp.get("/my-certificates")
@login_required
def my_certs():
    user_id = flask_session.get("user_id")
    certs = db.session.query(Certificate).filter_by(user_id=user_id).all()
    return render_template("my_certificates.html", certs=certs)


@bp.get("/certificates/<int:cert_id>")
@login_required
def download_certificate(cert_id: int):
    cert = db.session.get(Certificate, cert_id)
    if not cert:
        abort(404)
    user_id = flask_session.get("user_id")
    user = db.session.get(User, user_id)
    if cert.user_id != user_id and not (
        user.is_kt_admin
        or user.is_kt_crm
        or user.is_kt_delivery
        or user.is_kt_staff
    ):
        abort(403)
    return send_file(cert.file_path, as_attachment=True)
