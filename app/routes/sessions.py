from __future__ import annotations

import csv
import io
import os
import zipfile
from functools import wraps
from typing import Iterable

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session as flask_session,
    url_for,
)

from ..app import db, User
from ..certgen import make_certificate_pdf
from ..models import Certificate, Participant, Session, SessionParticipant

bp = Blueprint("sessions", __name__, url_prefix="/sessions")


def staff_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        user = db.session.get(User, user_id)
        if not user or not (
            user.is_kt_admin
            or user.is_kt_crm
            or user.is_kt_delivery
            or user.is_kt_staff
        ):
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


@bp.get("")
@staff_required
def list_sessions(current_user):
    sessions = db.session.query(Session).order_by(Session.start_date).all()
    return render_template("sessions.html", sessions=sessions)


@bp.get("/<int:session_id>")
@staff_required
def session_detail(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    links = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id)
        .all()
    )
    participants: list[Participant] = []
    for l in links:
        p = db.session.get(Participant, l.participant_id)
        if p:
            participants.append(p)
    certs_exist = (
        db.session.query(Certificate)
        .filter_by(session_id=session_id)
        .count()
        > 0
    )
    return render_template(
        "session_detail.html",
        session=sess,
        participants=participants,
        certs_exist=certs_exist,
    )


@bp.post("/<int:session_id>/participants/import")
@staff_required
def import_participants(session_id: int, current_user):
    file = request.files.get("csv")
    if not file:
        flash("No file uploaded", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    data = file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(data))
    count = 0
    for row in reader:
        email = (row.get("email") or "").strip().lower()
        if not email:
            continue
        full_name = (row.get("full_name") or "").strip()
        cert_name = (row.get("cert_name") or "").strip() or None
        participant = (
            db.session.query(Participant).filter_by(email=email).one_or_none()
        )
        if not participant:
            participant = Participant(
                email=email, full_name=full_name, cert_name_override=cert_name
            )
            db.session.add(participant)
            db.session.flush()
        else:
            participant.full_name = full_name or participant.full_name
            if cert_name:
                participant.cert_name_override = cert_name
        link = (
            db.session.query(SessionParticipant)
            .filter_by(session_id=session_id, participant_id=participant.id)
            .one_or_none()
        )
        if not link:
            db.session.add(
                SessionParticipant(session_id=session_id, participant_id=participant.id)
            )
        count += 1
    db.session.commit()
    flash(f"Imported {count} participants", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/participants/save")
@staff_required
def save_participants(session_id: int, current_user):
    for key, value in request.form.items():
        if key.startswith("cert_name_"):
            pid = int(key.split("_")[2])
            p = db.session.get(Participant, pid)
            if p:
                p.cert_name_override = value or None
    db.session.commit()
    flash("Participants updated", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/certs/generate")
@staff_required
def generate_certs(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    links = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id)
        .all()
    )
    count = 0
    for l in links:
        p = db.session.get(Participant, l.participant_id)
        if not p:
            continue
        cert_name = p.cert_name_override or p.full_name or p.email
        workshop_name = sess.title or ""
        completion_date = sess.end_date
        folder = f"/srv/certs/{session_id}"
        file_path = os.path.join(folder, f"{p.email}.pdf")
        file_hash = make_certificate_pdf(
            file_path, name=cert_name, workshop=workshop_name, date=completion_date
        )
        user = db.session.query(User).filter_by(email=p.email).one_or_none()
        cert = (
            db.session.query(Certificate)
            .filter_by(session_id=session_id, participant_email=p.email)
            .one_or_none()
        )
        if not cert:
            cert = Certificate(session_id=session_id, participant_email=p.email)
            db.session.add(cert)
        cert.user_id = user.id if user else None
        cert.full_name = p.full_name
        cert.cert_name = cert_name
        cert.workshop_name = workshop_name
        cert.completion_date = completion_date
        cert.file_path = file_path
        cert.file_hash = file_hash
        count += 1
    db.session.commit()
    flash(f"Generated {count} certificates", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.get("/<int:session_id>/certs.zip")
@staff_required
def certs_zip(session_id: int, current_user):
    folder = f"/srv/certs/{session_id}"
    if not os.path.isdir(folder):
        abort(404)
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w") as zf:
        for fname in os.listdir(folder):
            path = os.path.join(folder, fname)
            if os.path.isfile(path):
                zf.write(path, arcname=fname)
    mem.seek(0)
    return send_file(
        mem,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"certs_{session_id}.zip",
    )
