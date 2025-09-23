from __future__ import annotations

from collections import defaultdict
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    session as flask_session,
    url_for,
)
from sqlalchemy.orm import joinedload, selectinload

from ..app import db, User
from ..models import (
    Client,
    Participant,
    Session,
    SessionParticipant,
    Certificate,
    Resource,
    resource_workshop_types,
)
from ..shared.acl import is_delivery, is_contractor, is_kt_staff
from ..shared.prework_summary import get_session_prework_summary
from ..shared.prework_status import (
    get_participant_prework_status,
    summarize_prework_status,
)
from ..shared.sessions_lifecycle import is_material_only_session
from ..shared.certificates import get_template_mapping

bp = Blueprint("workshops", __name__, url_prefix="/workshops")


def facilitator_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login"))
        user = db.session.get(User, user_id)
        if not user or not (is_delivery(user) or is_contractor(user)):
            flash("Workshop view is available to assigned facilitators only.", "error")
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


@bp.get("/<int:session_id>")
@facilitator_required
def workshop_view(session_id: int, current_user):
    session = (
        db.session.query(Session)
        .options(
            joinedload(Session.client).joinedload(Client.crm),
            joinedload(Session.lead_facilitator),
            selectinload(Session.facilitators),
            joinedload(Session.workshop_type),
            joinedload(Session.simulation_outline),
            joinedload(Session.workshop_location),
            joinedload(Session.shipping_location),
            selectinload(Session.attendance_records),
        )
        .filter(Session.id == session_id)
        .one_or_none()
    )
    if not session:
        abort(404)

    material_only = is_material_only_session(session)

    is_assigned = False
    if session.lead_facilitator_id and session.lead_facilitator_id == current_user.id:
        is_assigned = True
    elif session.facilitators:
        is_assigned = any(f.id == current_user.id for f in session.facilitators)

    if not is_assigned:
        flash("Workshop view is available to assigned facilitators only.", "error")
        abort(403)

    if material_only:
        flash("Material only sessions use the session detail view.", "info")
        return redirect(url_for("sessions.session_detail", session_id=session.id))

    facilitator_resources: list[Resource] = []
    if session.workshop_type_id:
        facilitator_resources = (
            Resource.query.filter(Resource.active == True)
            .join(resource_workshop_types)
            .filter(resource_workshop_types.c.workshop_type_id == session.workshop_type_id)
            .filter(Resource.language == (session.workshop_language or "en"))
            .filter(Resource.audience.in_(["Facilitator", "Both"]))
            .order_by(Resource.name)
            .all()
        )

    participants: list[dict[str, object]] = []
    badge_filename = None
    import_errors = None
    attendance_days: list[int] = []
    attendance_map: dict[int, dict[int, bool]] = {}
    if not material_only:
        rows = (
            db.session.query(SessionParticipant, Participant, Certificate.pdf_path)
            .join(Participant, SessionParticipant.participant_id == Participant.id)
            .outerjoin(
                Certificate,
                (Certificate.session_id == session_id)
                & (Certificate.participant_id == Participant.id),
            )
            .filter(SessionParticipant.session_id == session_id)
            .all()
        )
        statuses = get_participant_prework_status(session.id)
        participants = []
        for link, participant, pdf_path in rows:
            status = statuses.get(participant.id)
            participants.append(
                {
                    "participant": participant,
                    "link": link,
                    "pdf_path": pdf_path,
                    "prework_status": status,
                    "prework_summary": summarize_prework_status(status),
                }
            )
        attendance_days = list(
            range(1, (session.number_of_class_days or 0) + 1)
        )
        if attendance_days:
            attendance_map = defaultdict(dict)
            for record in session.attendance_records:
                attendance_map[record.participant_id][record.day_index] = bool(
                    record.attended
                )
            for entry in participants:
                participant_id = entry["participant"].id
                entry["attendance"] = attendance_map.get(participant_id, {})
        import_errors = flask_session.pop("import_errors", None)
        mapping, _ = get_template_mapping(session)
        if mapping:
            badge_filename = mapping.badge_filename

    can_send_prework = bool(
        is_kt_staff(current_user)
        or is_delivery(current_user)
        or is_contractor(current_user)
    )

    can_manage_attendance = bool(
        attendance_days
        and (
            is_kt_staff(current_user)
            or is_delivery(current_user)
            or is_contractor(current_user)
        )
    )

    return render_template(
        "sessions/workshop_view.html",
        session=session,
        participants=participants,
        badge_filename=badge_filename,
        import_errors=import_errors,
        facilitator_resources=facilitator_resources,
        prework_summary=get_session_prework_summary(
            session.id, session_language=session.workshop_language
        ),
        can_send_prework=can_send_prework,
        current_user=current_user,
        attendance_days=attendance_days,
        can_manage_attendance=can_manage_attendance,
    )
