from functools import wraps

from flask import abort, redirect, session, url_for, flash

from ..app import db, User
from ..models import Session


def app_admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login"))
        user = db.session.get(User, user_id)
        if not user or not user.is_app_admin:
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


def admin_required(fn):
    """Allow access to SysAdmin or Administrator users."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login"))
        user = db.session.get(User, user_id)
        if not user or not (user.is_app_admin or user.is_admin):
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


def csa_allowed_for_session(fn=None, *, allow_delivered_view=False):
    """Allow staff or the session's CSA; block CSA if delivered unless viewing."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(session_id: int, *args, **kwargs):
            sess = db.session.get(Session, session_id)
            if not sess:
                abort(404)
            user_id = session.get("user_id")
            if user_id:
                user = db.session.get(User, user_id)
                if user and (user.is_app_admin or user.is_admin):
                    return fn(
                        session_id,
                        *args,
                        **kwargs,
                        sess=sess,
                        current_user=user,
                        csa_view=False,
                    )
            account_id = session.get("participant_account_id")
            if account_id and sess.csa_account_id == account_id:
                if sess.delivered and not allow_delivered_view:
                    abort(403)
                return fn(
                    session_id,
                    *args,
                    **kwargs,
                    sess=sess,
                    current_user=None,
                    csa_view=True,
                )
            if not user_id and not account_id:
                flash("Please log in to administer this session.", "error")
                return redirect(url_for("auth.login"))
            abort(403)

        return wrapper

    if fn is None:
        return decorator
    return decorator(fn)

