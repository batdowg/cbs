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

import os

from ..app import db, User
from ..models import Certificate, Participant

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
    user = db.session.get(User, user_id)
    email = (user.email or "").lower()
    certs = (
        db.session.query(Certificate)
        .join(Participant, Certificate.participant_id == Participant.id)
        .filter(db.func.lower(Participant.email) == email)
        .all()
    )
    return render_template("my_certificates.html", certs=certs)


@bp.get("/certificates/<int:cert_id>")
@login_required
def download_certificate(cert_id: int):
    cert = db.session.get(Certificate, cert_id)
    if not cert:
        abort(404)
    user_id = flask_session.get("user_id")
    user = db.session.get(User, user_id)
    participant = db.session.get(Participant, cert.participant_id)
    email = (user.email or "").lower()
    if participant and participant.email.lower() == email:
        allowed = True
    else:
        allowed = bool(user.is_app_admin or user.is_admin)
    if not allowed:
        abort(403)
    return send_file(os.path.join("/srv", cert.pdf_path), as_attachment=True)
