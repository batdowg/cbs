from __future__ import annotations

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
from ..models import Client, Participant, Session, SessionParticipant, Certificate
from ..shared.acl import is_delivery, is_contractor
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
        )
        .filter(Session.id == session_id)
        .one_or_none()
    )
    if not session:
        abort(404)

    is_assigned = False
    if session.lead_facilitator_id and session.lead_facilitator_id == current_user.id:
        is_assigned = True
    elif session.facilitators:
        is_assigned = any(f.id == current_user.id for f in session.facilitators)

    if not is_assigned:
        flash("Workshop view is available to assigned facilitators only.", "error")
        abort(403)

    participants: list[dict[str, object]] = []
    badge_filename = None
    if not session.materials_only:
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
        participants = [
            {"participant": participant, "link": link, "pdf_path": pdf_path}
            for link, participant, pdf_path in rows
        ]
        mapping, _ = get_template_mapping(session)
        if mapping:
            badge_filename = mapping.badge_filename

    return render_template(
        "sessions/workshop_view.html",
        session=session,
        participants=participants,
        badge_filename=badge_filename,
    )
