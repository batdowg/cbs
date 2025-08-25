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
    request,
    flash,
)

import os

from sqlalchemy import func

from ..app import db, User
from ..models import Certificate, Participant, ParticipantAccount

bp = Blueprint("learner", __name__)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in flask_session and "participant_account_id" not in flask_session:
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)

    return wrapper


@bp.get("/my-certificates")
@login_required
def my_certs():
    if flask_session.get("user_id"):
        user = db.session.get(User, flask_session.get("user_id"))
        email = (user.email or "").lower()
    else:
        account = db.session.get(
            ParticipantAccount, flask_session.get("participant_account_id")
        )
        email = (account.email or "").lower() if account else ""
    certs = (
        db.session.query(Certificate)
        .join(Participant, Certificate.participant_id == Participant.id)
        .filter(db.func.lower(Participant.email) == email)
        .all()
    )
    return render_template("my_certificates.html", certs=certs)


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if flask_session.get("user_id"):
        user = db.session.get(User, flask_session.get("user_id"))
        email = (user.email or "").lower()
        default_name = user.full_name or ""
    else:
        account = db.session.get(
            ParticipantAccount, flask_session.get("participant_account_id")
        )
        email = (account.email or "").lower() if account else ""
        default_name = account.full_name if account else ""
    account = (
        db.session.query(ParticipantAccount)
        .filter(func.lower(ParticipantAccount.email) == email)
        .one_or_none()
    )
    if not account:
        account = ParticipantAccount(email=email, full_name=default_name, is_active=True)
        account.certificate_name = default_name
        db.session.add(account)
        db.session.commit()
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()[:200]
        cert_name = (request.form.get("certificate_name") or "").strip()[:200]
        account.full_name = full_name
        account.certificate_name = cert_name or full_name
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("learner.profile"))
    return render_template(
        "profile.html",
        email=email,
        full_name=account.full_name or "",
        certificate_name=account.certificate_name or "",
    )


@bp.get("/certificates/<int:cert_id>")
@login_required
def download_certificate(cert_id: int):
    cert = db.session.get(Certificate, cert_id)
    if not cert:
        abort(404)
    user_id = flask_session.get("user_id")
    participant = db.session.get(Participant, cert.participant_id)
    if user_id:
        user = db.session.get(User, user_id)
        email = (user.email or "").lower()
        staff = bool(user.is_app_admin or user.is_admin)
    else:
        account = db.session.get(
            ParticipantAccount, flask_session.get("participant_account_id")
        )
        email = (account.email or "").lower() if account else ""
        staff = False
    if participant and participant.email.lower() == email:
        allowed = True
    else:
        allowed = staff
    if not allowed:
        abort(403)
    return send_file(os.path.join("/srv", cert.pdf_path), as_attachment=True)
