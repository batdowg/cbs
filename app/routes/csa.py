from __future__ import annotations

from flask import Blueprint, redirect, render_template, session as flask_session, url_for

from ..app import db
from ..models import Session
from .learner import login_required

bp = Blueprint("csa", __name__, url_prefix="/csa")


@bp.get("/my-sessions")
@login_required
def my_sessions():
    account_id = flask_session.get("participant_account_id")
    if not account_id:
        return redirect(url_for("auth.login"))
    sessions = (
        db.session.query(Session)
        .filter(Session.csa_account_id == account_id)
        .order_by(Session.start_date)
        .all()
    )
    return render_template("csa/my_sessions.html", sessions=sessions)
