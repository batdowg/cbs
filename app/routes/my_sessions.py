from __future__ import annotations

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
)
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from datetime import date

from ..app import db, User
from ..models import (
    Session,
    Client,
    Participant,
    ParticipantAccount,
    SessionParticipant,
    PreworkAssignment,
    Certificate,
)
from ..shared.acl import is_admin, is_contractor, is_delivery, is_kcrm
from .learner import login_required

bp = Blueprint("my_sessions", __name__, url_prefix="/my-sessions")


@bp.get("")
@login_required
def list_my_sessions():
    show_all = request.args.get("all") == "1"
    query = db.session.query(Session)
    user_id = flask_session.get("user_id")
    account_id = flask_session.get("participant_account_id")
    if user_id:
        if not show_all:
            query = query.filter(
                Session.finalized.is_(False), Session.cancelled.is_(False)
            )
        user = db.session.get(User, user_id)
        query = query.options(selectinload(Session.facilitators))
        is_delivery_role = is_delivery(user)
        is_contractor_role = is_contractor(user)
        is_crm_only = is_kcrm(user) and not (
            is_delivery_role or is_contractor_role or is_admin(user)
        )
        if is_crm_only:
            query = query.filter(Session.client.has(Client.crm_user_id == user.id))
        else:
            query = query.filter(
                or_(
                    Session.lead_facilitator_id == user.id,
                    Session.facilitators.any(User.id == user.id),
                    Session.client.has(Client.crm_user_id == user.id),
                )
            )
        sessions = query.order_by(Session.start_date).all()
        assigned_session_ids = {
            s.id
            for s in sessions
            if (s.lead_facilitator_id == user.id)
            or any(f.id == user.id for f in getattr(s, "facilitators", []))
        }
        use_workshop_view = is_delivery_role or is_contractor_role
        show_edit_button = bool(
            is_admin(user)
            or is_kcrm(user)
            or (is_delivery_role and not is_contractor_role)
        )
        return render_template(
            "my_sessions.html",
            sessions=sessions,
            show_all=show_all,
            assigned_session_ids=assigned_session_ids,
            workshop_link_for_facilitator=use_workshop_view,
            show_edit_button=show_edit_button,
        )
    elif account_id:
        account = db.session.get(ParticipantAccount, account_id)
        if not account:
            return redirect(url_for("auth.login"))
        sessions = (
            db.session.query(Session)
            .join(SessionParticipant, SessionParticipant.session_id == Session.id)
            .join(Participant, SessionParticipant.participant_id == Participant.id)
            .filter(Participant.account_id == account_id)
            .filter(Session.materials_only.is_(False))
            .order_by(Session.start_date)
            .all()
        )
        assignment_rows = (
            PreworkAssignment.query.outerjoin(
                Session, Session.id == PreworkAssignment.session_id
            )
            .filter(PreworkAssignment.participant_account_id == account_id)
            .filter(
                func.lower(func.trim(func.coalesce(Session.delivery_type, "")))
                != "certificate only"
            )
            .all()
        )
        assignments = {a.session_id: a for a in assignment_rows}
        certs = {
            c.session_id: c
            for c in db.session.query(Certificate)
            .join(Participant, Certificate.participant_id == Participant.id)
            .filter(Participant.account_id == account_id)
            .all()
        }
        return render_template(
            "my_sessions.html",
            sessions=sessions,
            assignments=assignments,
            certs=certs,
            today=date.today(),
            show_edit_button=False,
        )
    else:
        return redirect(url_for("auth.login"))
