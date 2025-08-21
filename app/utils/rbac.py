from functools import wraps

from flask import abort, redirect, session, url_for

from ..app import db, User


def app_admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
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
            return redirect(url_for("login"))
        user = db.session.get(User, user_id)
        if not user or not (user.is_app_admin or user.is_admin):
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper

