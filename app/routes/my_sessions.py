from __future__ import annotations

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
)
from sqlalchemy import or_
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
from .learner import login_required

bp = Blueprint("my_sessions", __name__, url_prefix="/my-sessions")


@bp.get("")
@login_required
def list_my_sessions():
    show_all = request.args.get("all") == "1"
    query = db.session.query(Session)
    query = query.filter(Session.materials_only.is_(False))
    user_id = flask_session.get("user_id")
    account_id = flask_session.get("participant_account_id")
    if user_id:
        if not show_all:
            query = query.filter(
                Session.finalized.is_(False), Session.cancelled.is_(False)
            )
        user = db.session.get(User, user_id)
        sessions = (
            query.filter(
                or_(
                    Session.lead_facilitator_id == user.id,
                    Session.facilitators.any(User.id == user.id),
                    Session.client.has(Client.crm_user_id == user.id),
                )
            )
            .order_by(Session.start_date)
            .all()
        )
        return render_template("my_sessions.html", sessions=sessions, show_all=show_all)
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
        assignments = {
            a.session_id: a
            for a in PreworkAssignment.query.filter_by(
                participant_account_id=account_id
            ).all()
        }
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
        )
    else:
        return redirect(url_for("auth.login"))
