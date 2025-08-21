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

from ..app import db, User
from ..models import Session, Client
from .learner import login_required

bp = Blueprint("my_sessions", __name__, url_prefix="/my-sessions")


@bp.get("")
@login_required
def list_my_sessions():
    show_all = request.args.get("all") == "1"
    query = db.session.query(Session)
    if not show_all:
        query = query.filter(Session.status.notin_(["Closed", "Cancelled"]))
    user_id = flask_session.get("user_id")
    account_id = flask_session.get("participant_account_id")
    if user_id:
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
    elif account_id:
        sessions = (
            query.filter(Session.csa_account_id == account_id)
            .order_by(Session.start_date)
            .all()
        )
    else:
        return redirect(url_for("login"))
    return render_template("my_sessions.html", sessions=sessions, show_all=show_all)
