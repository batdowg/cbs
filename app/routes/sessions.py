from __future__ import annotations

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
from ..models import Participant, Session, SessionParticipant, WorkshopType, AuditLog
from sqlalchemy import or_
from ..utils.certificates import generate_for_session

bp = Blueprint("sessions", __name__, url_prefix="/sessions")


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
            language=request.form.get("language") or None,
            capacity=request.form.get("capacity") or None,
            status=request.form.get("status") or None,
            sponsor=request.form.get("sponsor") or None,
            notes=request.form.get("notes") or None,
            simulation_outline=request.form.get("simulation_outline") or None,
        )
        sess.workshop_type = wt
        fac_ids = request.form.getlist("facilitators")
        if fac_ids:
            sess.facilitators = User.query.filter(User.id.in_(fac_ids)).all()
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
        return redirect(url_for("sessions.session_detail", session_id=sess.id))
    return render_template(
        "sessions/form.html",
        session=None,
        workshop_types=workshop_types,
        facilitators=facilitators,
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
        sess.title = request.form.get("title")
        sess.start_date = request.form.get("start_date") or None
        sess.end_date = request.form.get("end_date") or None
        sess.daily_start_time = request.form.get("daily_start_time") or None
        sess.daily_end_time = request.form.get("daily_end_time") or None
        sess.timezone = request.form.get("timezone") or None
        sess.location = request.form.get("location") or None
        sess.delivery_type = request.form.get("delivery_type") or None
        sess.region = request.form.get("region") or None
        sess.language = request.form.get("language") or None
        sess.capacity = request.form.get("capacity") or None
        sess.status = request.form.get("status") or None
        sess.sponsor = request.form.get("sponsor") or None
        sess.notes = request.form.get("notes") or None
        sess.simulation_outline = request.form.get("simulation_outline") or None
        fac_ids = request.form.getlist("facilitators")
        sess.facilitators = (
            User.query.filter(User.id.in_(fac_ids)).all() if fac_ids else []
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
        return redirect(url_for("sessions.session_detail", session_id=sess.id))
    return render_template(
        "sessions/form.html",
        session=sess,
        workshop_types=workshop_types,
        facilitators=facilitators,
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
    return render_template("session_detail.html", session=sess, participants=participants)


@bp.post("/<int:session_id>/participants/add")
@staff_required
def add_participant(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    email = (request.form.get("email") or "").strip().lower()
    full_name = (request.form.get("full_name") or "").strip()
    if not email:
        flash("Email required", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    participant = (
        db.session.query(Participant)
        .filter(db.func.lower(Participant.email) == email)
        .one_or_none()
    )
    if not participant:
        participant = Participant(email=email, full_name=full_name)
        db.session.add(participant)
        db.session.flush()
    else:
        participant.full_name = participant.full_name or full_name
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
