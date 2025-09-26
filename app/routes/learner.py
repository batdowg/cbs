from __future__ import annotations

from functools import wraps

from functools import wraps
import re

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
    current_app,
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
from ..models import Resource, resource_workshop_types
from ..shared.languages import get_language_options, code_to_label
from ..shared.storage import badge_png_exists, build_badge_public_url
from ..shared.profile_images import (
    delete_profile_image,
    ProfileImageError,
    resolve_profile_image,
    save_profile_image,
)
from ..shared.time import fmt_time_range_with_tz
from ..shared.names import combine_first_last, split_full_name

import time

bp = Blueprint("learner", __name__)

autosave_hits: dict[int, list[float]] = {}


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if (
            "user_id" not in flask_session
            and "participant_account_id" not in flask_session
        ):
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
        account = ParticipantAccount.query.filter(
            func.lower(ParticipantAccount.email) == email
        ).first()
        account_id = account.id if account else None
    else:
        return redirect(url_for("auth.login"))

    sessions = (
        db.session.query(Session)
        .options(
            joinedload(Session.workshop_type),
            joinedload(Session.client),
            joinedload(Session.facilitators),
            joinedload(Session.lead_facilitator),
            joinedload(Session.workshop_location),
        )
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
    cards: list[dict] = []
    for sess in sessions:
        workshop_name = (
            sess.workshop_type.name if sess.workshop_type else (sess.title or "Workshop")
        )
        language_label = code_to_label(sess.workshop_language or "")
        start_label = (
            sess.start_date.strftime("%-d %b %Y")
            if getattr(sess, "start_date", None)
            else "Date TBD"
        )
        end_label = (
            sess.end_date.strftime("%-d %b %Y")
            if getattr(sess, "end_date", None)
            else None
        )
        if end_label and sess.end_date == sess.start_date:
            end_label = None
        date_range = start_label if not end_label else f"{start_label} – {end_label}"

        location_text = (sess.location or "").strip()
        if not location_text and sess.workshop_location:
            pieces = [sess.workshop_location.label]
            city_bits = [sess.workshop_location.city, sess.workshop_location.country]
            city_bits = [p for p in city_bits if p]
            extra = ", ".join(city_bits)
            if extra:
                pieces.append(extra)
            location_text = " – ".join([p for p in pieces if p])
        if not location_text:
            location_text = "Location TBD"

        assignment = assignments.get(sess.id) if assignments else None
        has_prework = (
            not sess.prework_disabled
            and assignment
            and assignment.status != "WAIVED"
        )
        prework_url = (
            url_for("learner.prework_form", assignment_id=assignment.id)
            if has_prework
            else None
        )

        facilitators: list[dict] = []
        seen: set[int] = set()
        candidates = []
        if sess.lead_facilitator:
            candidates.append(sess.lead_facilitator)
        candidates.extend(sess.facilitators or [])
        for fac in candidates:
            if not fac or fac.id in seen:
                continue
            if not (fac.is_kt_delivery or fac.is_kt_contractor):
                continue
            seen.add(fac.id)
            facilitators.append(
                {
                    "id": fac.id,
                    "name": fac.full_name or fac.email,
                    "email": fac.email,
                    "phone": (fac.phone or "").strip(),
                    "photo": resolve_profile_image(fac.profile_image_path),
                }
            )

        cards.append(
            {
                "session_id": sess.id,
                "header": f"{workshop_name} – {start_label} – {language_label}",
                "prework_url": prework_url,
                "location": location_text,
                "date_range": date_range,
                "time_range": fmt_time_range_with_tz(
                    sess.daily_start_time, sess.daily_end_time, sess.timezone
                )
                or "",
                "facilitators": facilitators,
            }
        )

    return render_template(
        "my_workshops.html",
        cards=cards,
        fallback_avatar="img/avatar_silhouette.png",
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
    sessions = (
        db.session.query(Session)
        .options(joinedload(Session.workshop_type))
        .join(SessionParticipant, SessionParticipant.session_id == Session.id)
        .join(Participant, SessionParticipant.participant_id == Participant.id)
        .filter(func.lower(Participant.email) == email)
        .filter(Session.start_date != None, Session.start_date <= today)
        .all()
    )
    workshop_languages: dict[int, set[str]] = {}
    workshop_types: dict[int, "WorkshopType"] = {}
    for sess in sessions:
        wt = sess.workshop_type
        if not wt:
            continue
        workshop_types.setdefault(wt.id, wt)
        lang = (sess.workshop_language or "en")
        workshop_languages.setdefault(wt.id, set()).add(lang)
    grouped: list[tuple["WorkshopType", list[Resource]]] = []
    for wt_id, wt in sorted(
        ((wt_id, wt) for wt_id, wt in workshop_types.items()),
        key=lambda item: item[1].name,
    ):
        languages = workshop_languages.get(wt_id, {"en"})
        try:
            items = (
                Resource.query.filter(Resource.active == True)
                .join(resource_workshop_types)
                .filter(resource_workshop_types.c.workshop_type_id == wt_id)
                .filter(Resource.language.in_(languages))
                .filter(Resource.audience.in_(["Participant", "Both"]))
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
        PreworkAssignment.query.outerjoin(
            Session, Session.id == PreworkAssignment.session_id
        )
        .filter(PreworkAssignment.participant_account_id == account_id)
        .filter(
            func.lower(func.trim(func.coalesce(Session.delivery_type, "")))
            != "certificate only"
        )
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
    if assignment.session and assignment.session.delivered:
        flash("Prework closed after delivery", "error")
        return redirect(url_for("learner.my_prework"))
    questions = assignment.snapshot_json.get("questions", [])
    answers: dict[int, dict[int, str]] = {}
    for ans in assignment.answers:
        answers.setdefault(ans.question_index, {})[ans.item_index] = ans.answer_text
    if request.method == "POST":
        for q in questions:
            q_index = q.get("index")
            if q_index is None:
                continue
            values = request.form.getlist(f"answers[{q_index}][]")
            if not values:
                legacy_value = request.form.get(f"q{q_index}")
                if legacy_value:
                    values = [legacy_value]
            cleaned = [value.strip() for value in values if value and value.strip()]
            existing_answers = sorted(
                (
                    ans
                    for ans in assignment.answers
                    if ans.question_index == q_index
                ),
                key=lambda ans: ans.item_index or 0,
            )
            for item_idx, text in enumerate(cleaned):
                if item_idx < len(existing_answers):
                    ans = existing_answers[item_idx]
                    ans.item_index = item_idx
                    ans.answer_text = text
                else:
                    db.session.add(
                        PreworkAnswer(
                            assignment_id=assignment.id,
                            question_index=q_index,
                            item_index=item_idx,
                            answer_text=text,
                        )
                    )
            for leftover in existing_answers[len(cleaned) :]:
                db.session.delete(leftover)
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
    if assignment.session and assignment.session.delivered:
        abort(403)
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
    account_id = flask_session.get("participant_account_id")
    if not account_id and flask_session.get("user_id"):
        user = db.session.get(User, flask_session.get("user_id"))
        account = (
            db.session.query(ParticipantAccount)
            .filter(func.lower(ParticipantAccount.email) == (user.email or "").lower())
            .one_or_none()
        )
        account_id = account.id if account else None
    certs = []
    if account_id:
        certs = (
            db.session.query(Certificate)
            .join(Participant, Certificate.participant_id == Participant.id)
            .filter(Participant.account_id == account_id)
            .options(joinedload(Certificate.session).joinedload(Session.workshop_type))
            .all()
        )
    for cert in certs:
        session = cert.session
        session_end_date = session.end_date if session else None
        public_url = build_badge_public_url(
            cert.session_id, session_end_date, cert.certification_number
        )
        has_png = False
        if public_url:
            has_png = badge_png_exists(
                cert.session_id, session_end_date, cert.certification_number
            )
        cert.badge_url = public_url if has_png else None
        cert.badge_available = has_png
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
            account.full_name = user.display_name
            if not account.certificate_name:
                account.certificate_name = user.display_name
            db.session.commit()
            flash("Names synchronized.", "success")
            return redirect(url_for("learner.profile"))
        first_name = (request.form.get("first_name") or "").strip()[:100]
        last_name = (request.form.get("last_name") or "").strip()[:100]
        fallback_full = (request.form.get("full_name") or "").strip()[:200]
        if not first_name and not last_name and fallback_full:
            split_first, split_last = split_full_name(fallback_full)
            if split_first:
                first_name = split_first[:100]
            if split_last:
                last_name = split_last[:100]
        display_name = combine_first_last(first_name, last_name)
        full_name = (display_name or fallback_full)[:200]
        pref_lang = (request.form.get("preferred_language") or "en")[:10]
        cert_name = (request.form.get("certificate_name") or "").strip()[:200]
        phone = (request.form.get("phone") or "").strip()[:50]
        city = (request.form.get("city") or "").strip()[:120]
        state = (request.form.get("state") or "").strip()[:120]
        country = (request.form.get("country") or "").strip()[:120]
        remove_photo = request.form.get("remove_photo") == "1"
        photo_file = request.files.get("profile_image")

        errors: list[str] = []
        if phone and not re.fullmatch(r"[0-9+()\-\s]+", phone):
            errors.append(
                "Phone number may include digits, spaces, parentheses, plus or hyphen."
            )
        if any([city, state, country]):
            if not city:
                errors.append("City is required when providing a location.")
            if not state and not country:
                errors.append("Add a state or country for your location.")

        owner_key: str | None = None
        existing_photo = None
        if user_id and user:
            owner_key = str(user.id)
            existing_photo = user.profile_image_path
        elif account:
            owner_key = f"participant-{account.id}"
            existing_photo = account.profile_image_path

        new_photo_path: str | None = None
        if photo_file and photo_file.filename:
            if not owner_key:
                errors.append("Unable to save profile photo right now.")
            else:
                try:
                    result = save_profile_image(
                        photo_file, owner_key, previous_path=existing_photo
                    )
                    new_photo_path = result.relative_path
                    remove_photo = False
                except ProfileImageError as exc:
                    errors.append(str(exc))

        if errors:
            for message in errors:
                flash(message, "error")
            return redirect(url_for("learner.profile"))

        if user_id:
            user.first_name = first_name or None
            user.last_name = last_name or None
            user.full_name = full_name or None
            user.title = (request.form.get("title") or "").strip()[:255]
            user.preferred_language = pref_lang
            user.phone = phone or None
            user.city = city or None
            user.state = state or None
            user.country = country or None
            if new_photo_path:
                user.profile_image_path = new_photo_path
            cert_value = cert_name or full_name
            if account:
                account.full_name = full_name or account.full_name
                account.certificate_name = cert_value
                account.preferred_language = pref_lang
                account.phone = phone or None
                account.city = city or None
                account.state = state or None
                account.country = country or None
                if new_photo_path:
                    account.profile_image_path = new_photo_path
            else:
                account = ParticipantAccount(
                    email=email,
                    full_name=full_name,
                    certificate_name=cert_name or full_name,
                    preferred_language=pref_lang,
                    is_active=True,
                    phone=phone or None,
                    city=city or None,
                    state=state or None,
                    country=country or None,
                    profile_image_path=new_photo_path,
                )
                db.session.add(account)
        else:
            if account:
                account.full_name = full_name or account.full_name
                account.certificate_name = cert_name or full_name
                account.preferred_language = pref_lang
                account.phone = phone or None
                account.city = city or None
                account.state = state or None
                account.country = country or None
                if new_photo_path:
                    account.profile_image_path = new_photo_path

        if email:
            participant_rows = (
                db.session.query(Participant)
                .filter(func.lower(Participant.email) == email)
                .all()
            )
            for participant in participant_rows:
                if first_name:
                    participant.first_name = first_name
                if last_name:
                    participant.last_name = last_name
                if full_name:
                    participant.full_name = full_name

        if remove_photo:
            to_clear = None
            if user_id and user:
                to_clear = user.profile_image_path
                user.profile_image_path = None
            if account:
                to_clear = to_clear or account.profile_image_path
                account.profile_image_path = None
            if to_clear:
                delete_profile_image(to_clear)
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("learner.profile"))
    first_val = ""
    last_val = ""
    display_val = ""
    if user_id and user:
        first_val = (user.first_name or "").strip()
        last_val = (user.last_name or "").strip()
        display_val = (user.display_name or "").strip()
        if not (first_val or last_val) and user.full_name:
            split_first, split_last = split_full_name(user.full_name)
            if split_first and not first_val:
                first_val = split_first
            if split_last and not last_val:
                last_val = split_last
    elif account:
        split_first, split_last = split_full_name(account.full_name or "")
        if split_first:
            first_val = split_first
        if split_last:
            last_val = split_last
        display_val = (account.full_name or "").strip()
    if not display_val:
        display_val = combine_first_last(first_val, last_val) or (
            (account.full_name or "") if account else ""
        )

    return render_template(
        "profile.html",
        email=email,
        first_name=first_val,
        last_name=last_val,
        display_name=display_val,
        certificate_name=(
            account.certificate_name
            if account
            else (display_val if user_id and user else "")
        ),
        preferred_language=(
            (user.preferred_language if user_id else account.preferred_language)
            if (user or account)
            else "en"
        ),
        title=user.title if user_id and user else "",
        is_staff=bool(user_id),
        has_participant=bool(account),
        language_options=get_language_options(),
        phone=(
            (user.phone if user_id else account.phone)
            if (user or account)
            else ""
        )
        or "",
        city=((user.city if user_id else account.city) if (user or account) else "") or "",
        state=((user.state if user_id else account.state) if (user or account) else "")
        or "",
        country=((user.country if user_id else account.country) if (user or account) else "")
        or "",
        profile_image_url=resolve_profile_image(
            (user.profile_image_path if user_id and user else None)
            or (account.profile_image_path if account else None)
        ),
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
    site_root = current_app.config.get("SITE_ROOT", "/srv")
    cert_root = os.path.join(site_root, "certificates")
    rel_path = (cert.pdf_path or "").lstrip("/")
    if rel_path.startswith("certificates/"):
        rel_path = rel_path.split("/", 1)[1]
    full_path = os.path.join(cert_root, rel_path)
    if not os.path.isfile(full_path):
        current_app.logger.warning("[CERT-MISSING] id=%s path=%s", cert.id, full_path)
        abort(404)
    return send_file(full_path, as_attachment=True, mimetype="application/pdf")
