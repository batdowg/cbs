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
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from ..app import db, User
from ..models import (
    Certificate,
    Participant,
    ParticipantAccount,
    Session,
    SessionParticipant,
    PreworkAssignment,
    PreworkAnswer,
)
from ..models import Resource, WorkshopType
from ..models import resource_workshop_types
from ..utils.languages import get_language_options

import time

bp = Blueprint("learner", __name__)

autosave_hits: dict[int, list[float]] = {}


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in flask_session and "participant_account_id" not in flask_session:
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)

    return wrapper


@bp.get("/my-workshops")
@login_required
def my_workshops():
    """List sessions where the current user is a participant."""
    account_id = flask_session.get("participant_account_id")
    user_id = flask_session.get("user_id")
    email = ""
    account = None
    if account_id:
        account = db.session.get(ParticipantAccount, account_id)
        email = (account.email or "").lower() if account else ""
    elif user_id:
        user = db.session.get(User, user_id)
        email = (user.email or "").lower()
        account = (
            ParticipantAccount.query.filter(
                func.lower(ParticipantAccount.email) == email
            ).first()
        )
        account_id = account.id if account else None
    else:
        return redirect(url_for("auth.login"))

    sessions = (
        db.session.query(Session)
        .join(SessionParticipant, SessionParticipant.session_id == Session.id)
        .join(Participant, SessionParticipant.participant_id == Participant.id)
        .filter(func.lower(Participant.email) == email)
        .order_by(Session.start_date)
        .all()
    )
    assignments = {}
    if account_id:
        assignments = {
            a.session_id: a
            for a in PreworkAssignment.query.filter_by(
                participant_account_id=account_id
            ).all()
        }
    return render_template(
        "my_workshops.html", sessions=sessions, assignments=assignments
    )


@bp.get("/my-resources")
@login_required
def my_resources():
    if flask_session.get("user_id"):
        user = db.session.get(User, flask_session.get("user_id"))
        email = (user.email or "").lower()
    else:
        account = db.session.get(
            ParticipantAccount, flask_session.get("participant_account_id")
        )
        email = (account.email or "").lower() if account else ""
    today = date.today()
    wt_query = (
        db.session.query(WorkshopType)
        .join(Session, Session.workshop_type_id == WorkshopType.id)
        .join(
            SessionParticipant,
            SessionParticipant.session_id == Session.id,
        )
        .join(Participant, SessionParticipant.participant_id == Participant.id)
        .filter(func.lower(Participant.email) == email)
        .filter(Session.start_date != None, Session.start_date <= today)
        .order_by(WorkshopType.name)
        .all()
    )
    seen_ids: set[int] = set()
    wtypes = []
    for wt in wt_query:
        if wt.id not in seen_ids:
            wtypes.append(wt)
            seen_ids.add(wt.id)
    grouped = []
    for wt in wtypes:
        try:
            items = (
                Resource.query.filter(Resource.active == True)
                .join(resource_workshop_types)
                .filter(resource_workshop_types.c.workshop_type_id == wt.id)
                .order_by(Resource.name)
                .all()
            )
        except Exception:
            items = []
        if items:
            grouped.append((wt, items))
    return render_template(
        "my_resources.html", grouped=grouped, active_nav="my-resources"
    )


@bp.get("/my-prework")
@login_required
def my_prework():
    account_id = flask_session.get("participant_account_id")
    if not account_id:
        return render_template(
            "my_prework.html", assignments=[], active_nav="my-prework"
        )
    assignments = (
        PreworkAssignment.query.filter_by(participant_account_id=account_id)
        .order_by(PreworkAssignment.due_at)
        .all()
    )
    return render_template(
        "my_prework.html", assignments=assignments, active_nav="my-prework"
    )


@bp.route("/prework/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def prework_form(assignment_id: int):
    account_id = flask_session.get("participant_account_id")
    if not account_id:
        abort(403)
    assignment = db.session.get(PreworkAssignment, assignment_id)
    if not assignment or assignment.participant_account_id != account_id:
        abort(404)
    questions = assignment.snapshot_json.get("questions", [])
    answers: dict[int, dict[int, str]] = {}
    for ans in assignment.answers:
        answers.setdefault(ans.question_index, {})[ans.item_index] = ans.answer_text
    if request.method == "POST":
        for q in questions:
            if q.get("kind") == "LIST":
                continue
            key = f"q{q['index']}"
            text = (request.form.get(key) or "").strip()
            existing = PreworkAnswer.query.filter_by(
                assignment_id=assignment.id,
                question_index=q["index"],
                item_index=0,
            ).first()
            if existing:
                existing.answer_text = text
            elif text:
                db.session.add(
                    PreworkAnswer(
                        assignment_id=assignment.id,
                        question_index=q["index"],
                        item_index=0,
                        answer_text=text,
                    )
                )
        db.session.commit()
        db.session.refresh(assignment)
        assignment.update_completion()
        db.session.commit()
        flash("Prework saved", "success")
        return redirect(url_for("learner.my_prework"))
    return render_template(
        "prework_form.html",
        assignment=assignment,
        questions=questions,
        answers=answers,
    )


@bp.post("/prework/<int:assignment_id>/autosave")
@login_required
def prework_autosave(assignment_id: int):
    account_id = flask_session.get("participant_account_id")
    user_id = flask_session.get("user_id")
    assignment = db.session.get(PreworkAssignment, assignment_id)
    if not assignment or (
        account_id != assignment.participant_account_id and not user_id
    ):
        abort(404)
    now = time.time()
    hits = autosave_hits.get(assignment_id, [])
    hits = [t for t in hits if now - t < 10]
    if len(hits) >= 10:
        return ("Too Many Requests", 429)
    hits.append(now)
    autosave_hits[assignment_id] = hits
    data = request.get_json() or {}
    q_idx = int(data.get("question_index", 0))
    item_idx = int(data.get("item_index", 0))
    text = (data.get("text") or "").strip()
    ans = PreworkAnswer.query.filter_by(
        assignment_id=assignment.id,
        question_index=q_idx,
        item_index=item_idx,
    ).first()
    if text:
        if ans:
            ans.answer_text = text
        else:
            db.session.add(
                PreworkAnswer(
                    assignment_id=assignment.id,
                    question_index=q_idx,
                    item_index=item_idx,
                    answer_text=text,
                )
            )
    else:
        if ans:
            db.session.delete(ans)
    db.session.commit()
    db.session.refresh(assignment)
    assignment.update_completion()
    db.session.commit()
    return {"status": "ok"}


@bp.get("/prework/<int:assignment_id>/download")
@login_required
def prework_download(assignment_id: int):
    account_id = flask_session.get("participant_account_id")
    user_id = flask_session.get("user_id")
    assignment = db.session.get(PreworkAssignment, assignment_id)
    if not assignment or (
        not user_id and assignment.participant_account_id != account_id
    ):
        abort(404)
    questions = assignment.snapshot_json.get("questions", [])
    answers: dict[int, dict[int, str]] = {}
    for ans in assignment.answers:
        answers.setdefault(ans.question_index, {})[ans.item_index] = ans.answer_text
    return render_template(
        "prework_download.html",
        assignment=assignment,
        questions=questions,
        answers=answers,
    )
    
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
        .options(joinedload(Certificate.session).joinedload(Session.workshop_type))
        .all()
    )
    return render_template("my_certificates.html", certs=certs)


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = flask_session.get("user_id")
    if user_id:
        user = db.session.get(User, user_id)
        email = (user.email or "").lower()
        account = (
            db.session.query(ParticipantAccount)
            .filter(func.lower(ParticipantAccount.email) == email)
            .one_or_none()
        )
    else:
        account = db.session.get(
            ParticipantAccount, flask_session.get("participant_account_id")
        )
        email = (account.email or "").lower() if account else ""
        user = None

    if request.method == "POST":
        form_kind = request.form.get("form")
        if form_kind == "password":
            pwd = request.form.get("password") or ""
            confirm = request.form.get("password_confirm") or ""
            if not pwd or pwd != confirm:
                flash("Passwords do not match", "error")
                return redirect(url_for("learner.profile") + "#password")
            target = user if user_id else account
            target.set_password(pwd)
            if hasattr(target, "must_change_password"):
                target.must_change_password = False
            db.session.commit()
            flash("Password updated.", "success")
            return redirect(url_for("learner.profile"))
        if form_kind == "sync" and user and account:
            account.full_name = user.full_name
            db.session.commit()
            flash("Names synchronized.", "success")
            return redirect(url_for("learner.profile"))
        full_name = (request.form.get("full_name") or "").strip()[:200]
        pref_lang = (request.form.get("preferred_language") or "en")[:10]
        cert_name = (request.form.get("certificate_name") or "").strip()[:200]
        if user_id:
            user.full_name = full_name
            user.title = (request.form.get("title") or "").strip()[:255]
            user.preferred_language = pref_lang
            cert_value = cert_name or full_name
            if account:
                account.certificate_name = cert_value
                account.preferred_language = pref_lang
            else:
                account = ParticipantAccount(
                    email=email,
                    full_name=full_name,
                    certificate_name=cert_value,
                    preferred_language=pref_lang,
                    is_active=True,
                )
                db.session.add(account)
        else:
            if account:
                account.full_name = full_name
                account.certificate_name = cert_name or full_name
                account.preferred_language = pref_lang
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("learner.profile"))
    return render_template(
        "profile.html",
        email=email,
        full_name=(user.full_name if user_id else account.full_name) if (user or account) else "",
        certificate_name=(account.certificate_name if account else (user.full_name if user_id and user else "")),
        preferred_language=(user.preferred_language if user_id else account.preferred_language) if (user or account) else "en",
        title=user.title if user_id and user else "",
        is_staff=bool(user_id),
        has_participant=bool(account),
        language_options=get_language_options(),
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
