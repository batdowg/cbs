from __future__ import annotations

import csv
import io
from functools import wraps

from flask import (
    Blueprint,
    Response,
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
    LANG_CHOICES,
    Participant,
    Session,
    SessionParticipant,
    WorkshopType,
    AuditLog,
)
from sqlalchemy import or_, func
from ..utils.certificates import generate_for_session
from ..utils.provisioning import (
    deactivate_orphan_accounts_for_session,
    provision_participant_accounts_for_session,
)

bp = Blueprint("sessions", __name__, url_prefix="/sessions")

STATUS_CHOICES = ["New", "Confirmed", "On Hold", "Delivered", "Closed", "Cancelled"]
ADVANCED_STATUSES = {"Confirmed", "Delivered", "Closed", "Cancelled"}


def staff_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
        user = db.session.get(User, user_id)
        if not user or not (user.is_app_admin or user.is_admin):
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


@bp.get("")
@staff_required
def list_sessions(current_user):
    sessions = db.session.query(Session).order_by(Session.start_date).all()
    return render_template("sessions.html", sessions=sessions)


@bp.route("/new", methods=["GET", "POST"])
@staff_required
def new_session(current_user):
    workshop_types = WorkshopType.query.order_by(WorkshopType.code).all()
    facilitators = User.query.filter(
        or_(User.is_kt_delivery == True, User.is_kt_contractor == True)
    ).all()
    if request.method == "POST":
        wt_id = request.form.get("workshop_type_id")
        if not wt_id:
            flash("Workshop Type required", "error")
            return redirect(url_for("sessions.new_session"))
        wt = db.session.get(WorkshopType, int(wt_id))
        language = request.form.get("language") or "English"
        allowed = [lbl for lbl, _ in LANG_CHOICES]
        if language not in allowed:
            language = "English"
        confirmed_ready = bool(request.form.get("confirmed_ready"))
        status = request.form.get("status") or "New"
        if not confirmed_ready and status in ADVANCED_STATUSES:
            flash("Cannot set advanced status without Confirmed-Ready", "error")
            status = "New"
        sess = Session(
            title=request.form.get("title"),
            start_date=request.form.get("start_date") or None,
            end_date=request.form.get("end_date") or None,
            daily_start_time=request.form.get("daily_start_time") or None,
            daily_end_time=request.form.get("daily_end_time") or None,
            timezone=request.form.get("timezone") or None,
            location=request.form.get("location") or None,
            delivery_type=request.form.get("delivery_type") or None,
            region=request.form.get("region") or None,
            language=language,
            capacity=request.form.get("capacity") or None,
            status=status,
            confirmed_ready=confirmed_ready,
            sponsor=request.form.get("sponsor") or None,
            notes=request.form.get("notes") or None,
            simulation_outline=request.form.get("simulation_outline") or None,
        )
        sess.workshop_type = wt
        lead_id = request.form.get("lead_facilitator_id")
        if lead_id:
            sess.lead_facilitator_id = int(lead_id)
        add_ids = [
            int(fid)
            for fid in request.form.getlist("additional_facilitators")
            if fid and fid != lead_id
        ]
        if add_ids:
            sess.facilitators = User.query.filter(User.id.in_(add_ids)).all()
        db.session.add(sess)
        db.session.flush()
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=sess.id,
                action="session_create",
                details=f"session_id={sess.id}",
            )
        )
        db.session.commit()
        if sess.confirmed_ready:
            summary = provision_participant_accounts_for_session(sess.id)
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    session_id=sess.id,
                    action="provision",
                    details=(
                        f"created={summary['created']} skipped={summary['skipped_staff']} reactivated={summary['reactivated']}"
                    ),
                )
            )
            db.session.commit()
        return redirect(url_for("sessions.session_detail", session_id=sess.id))
    return render_template(
        "sessions/form.html",
        session=None,
        workshop_types=workshop_types,
        facilitators=facilitators,
        LANG_CHOICES=LANG_CHOICES,
        STATUS_CHOICES=STATUS_CHOICES,
    )


@bp.route("/<int:session_id>/edit", methods=["GET", "POST"])
@staff_required
def edit_session(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    workshop_types = WorkshopType.query.order_by(WorkshopType.code).all()
    facilitators = User.query.filter(
        or_(User.is_kt_delivery == True, User.is_kt_contractor == True)
    ).all()
    if request.method == "POST":
        wt_id = request.form.get("workshop_type_id")
        if wt_id:
            sess.workshop_type = db.session.get(WorkshopType, int(wt_id))
        old_confirmed = sess.confirmed_ready
        old_status = sess.status or "New"
        sess.title = request.form.get("title")
        sess.start_date = request.form.get("start_date") or None
        sess.end_date = request.form.get("end_date") or None
        sess.daily_start_time = request.form.get("daily_start_time") or None
        sess.daily_end_time = request.form.get("daily_end_time") or None
        sess.timezone = request.form.get("timezone") or None
        sess.location = request.form.get("location") or None
        sess.delivery_type = request.form.get("delivery_type") or None
        sess.region = request.form.get("region") or None
        language = request.form.get("language") or "English"
        allowed = [lbl for lbl, _ in LANG_CHOICES]
        sess.language = language if language in allowed else "English"
        sess.capacity = request.form.get("capacity") or None
        confirmed_ready = bool(request.form.get("confirmed_ready"))
        status = request.form.get("status") or old_status
        if not confirmed_ready and status in ADVANCED_STATUSES:
            flash("Cannot set advanced status without Confirmed-Ready", "error")
            status = old_status if old_status in ["New", "On Hold"] else "New"
        sess.confirmed_ready = confirmed_ready
        sess.status = status
        sess.sponsor = request.form.get("sponsor") or None
        sess.notes = request.form.get("notes") or None
        sess.simulation_outline = request.form.get("simulation_outline") or None
        lead_id = request.form.get("lead_facilitator_id")
        sess.lead_facilitator_id = int(lead_id) if lead_id else None
        add_ids = [
            int(fid)
            for fid in request.form.getlist("additional_facilitators")
            if fid and fid != lead_id
        ]
        sess.facilitators = (
            User.query.filter(User.id.in_(add_ids)).all() if add_ids else []
        )
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=sess.id,
                action="session_update",
                details=f"session_id={sess.id}",
            )
        )
        db.session.commit()
        if confirmed_ready and not old_confirmed:
            summary = provision_participant_accounts_for_session(sess.id)
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    session_id=sess.id,
                    action="provision",
                    details=(
                        f"created={summary['created']} skipped={summary['skipped_staff']} reactivated={summary['reactivated']}"
                    ),
                )
            )
            db.session.commit()
        if sess.status in ["Cancelled", "On Hold"]:
            deactivated = deactivate_orphan_accounts_for_session(sess.id)
            if deactivated:
                db.session.add(
                    AuditLog(
                        user_id=current_user.id,
                        session_id=sess.id,
                        action="deactivate",
                        details=f"count={deactivated}",
                    )
                )
                db.session.commit()
        return redirect(url_for("sessions.session_detail", session_id=sess.id))
    return render_template(
        "sessions/form.html",
        session=sess,
        workshop_types=workshop_types,
        facilitators=facilitators,
        LANG_CHOICES=LANG_CHOICES,
        STATUS_CHOICES=STATUS_CHOICES,
    )


@bp.get("/<int:session_id>")
@staff_required
def session_detail(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    links = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id)
        .join(Participant, SessionParticipant.participant_id == Participant.id)
        .all()
    )
    participants = []
    for link in links:
        participant = db.session.get(Participant, link.participant_id)
        if participant:
            participants.append({"participant": participant, "link": link})
    import_errors = flask_session.pop("import_errors", None)
    return render_template(
        "session_detail.html", session=sess, participants=participants, import_errors=import_errors
    )


@bp.post("/<int:session_id>/participants/add")
@staff_required
def add_participant(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    email = (request.form.get("email") or "").strip().lower()
    full_name = (request.form.get("full_name") or "").strip()
    title = (request.form.get("title") or "").strip()
    if not email:
        flash("Email required", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    participant = (
        db.session.query(Participant)
        .filter(db.func.lower(Participant.email) == email)
        .one_or_none()
    )
    if not participant:
        participant = Participant(email=email, full_name=full_name, title=title)
        db.session.add(participant)
        db.session.flush()
    else:
        participant.full_name = participant.full_name or full_name
        if title:
            participant.title = participant.title or title
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant.id)
        .one_or_none()
    )
    if not link:
        link = SessionParticipant(
            session_id=session_id,
            participant_id=participant.id,
            completion_date=sess.end_date,
        )
        db.session.add(link)
    db.session.commit()
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.route("/<int:session_id>/participants/<int:participant_id>/edit", methods=["GET", "POST"])
@staff_required
def edit_participant(session_id: int, participant_id: int, current_user):
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant_id)
        .one_or_none()
    )
    if not link:
        abort(404)
    participant = db.session.get(Participant, participant_id)
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        title = (request.form.get("title") or "").strip()
        participant.full_name = full_name or None
        participant.title = title or None
        db.session.commit()
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    return render_template(
        "participant_edit.html", session_id=session_id, participant=participant
    )


@bp.post("/<int:session_id>/participants/<int:participant_id>/remove")
@staff_required
def remove_participant(session_id: int, participant_id: int, current_user):
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant_id)
        .one_or_none()
    )
    if link:
        db.session.delete(link)
        db.session.commit()
        flash("Participant removed", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.get("/<int:session_id>/participants/sample-csv")
@staff_required
def sample_csv(session_id: int, current_user):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["FullName", "Email", "Title"])
    writer.writerow(["Jane Doe", "jane@example.com", "Manager"])
    writer.writerow(["John Smith", "john@example.com", "Director"])
    resp = Response(output.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=sample.csv"
    return resp


@bp.post("/<int:session_id>/participants/import-csv")
@staff_required
def import_csv(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    file = request.files.get("file")
    if not file or not file.filename.endswith(".csv"):
        flash("CSV file required", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    text = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    errors: list[str] = []
    for idx, row in enumerate(reader, start=2):
        full_name = (row.get("FullName") or "").strip()
        email = (row.get("Email") or "").strip().lower()
        title = (row.get("Title") or "").strip()
        if not email or "@" not in email:
            errors.append(f"Row {idx}: invalid email '{email}'")
            continue
        participant = (
            db.session.query(Participant)
            .filter(func.lower(Participant.email) == email)
            .one_or_none()
        )
        if not participant:
            participant = Participant(
                email=email, full_name=full_name or None, title=title or None
            )
            db.session.add(participant)
            db.session.flush()
        else:
            if full_name:
                participant.full_name = full_name
            if title:
                participant.title = title
        link = (
            db.session.query(SessionParticipant)
            .filter_by(session_id=session_id, participant_id=participant.id)
            .one_or_none()
        )
        if not link:
            link = SessionParticipant(
                session_id=session_id,
                participant_id=participant.id,
                completion_date=sess.end_date,
            )
            db.session.add(link)
        imported += 1
    db.session.commit()
    flask_session["import_errors"] = errors
    flash(f"Imported {imported}, skipped {len(errors)}", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/participants/<int:participant_id>/generate")
@staff_required
def generate_single(session_id: int, participant_id: int, current_user):
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant_id)
        .one_or_none()
    )
    if not link:
        abort(404)
    action = request.form.get("action")
    if "completion_date" in request.form:
        link.completion_date = request.form.get("completion_date") or None
        db.session.commit()
    if action == "generate":
        participant = db.session.get(Participant, participant_id)
        generate_for_session(session_id, [participant.email])
        flash("Certificate generated", "success")
    else:
        flash("Participant updated", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/generate")
@staff_required
def generate_bulk(session_id: int, current_user):
    count, _ = generate_for_session(session_id)
    flash(f"Generated {count} certificates", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))
