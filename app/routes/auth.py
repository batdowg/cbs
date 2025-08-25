from __future__ import annotations

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
    current_app,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func

from ..app import db
from ..models import User, ParticipantAccount, AuditLog
from ..utils.auth_bridge import lookup_identity, verify_password, login_identity
from .. import emailer

bp = Blueprint("auth", __name__)


@bp.route("/", methods=["GET", "POST"])
@bp.route("/login", methods=["GET", "POST"], endpoint="login")
def login():
    if request.method == "POST":
        email_input = request.form.get("email", "")
        password = request.form.get("password", "")
        email = (email_input or "").strip().lower()
        try:
            parsed = validate_email(email_input)  # type: ignore
            email = parsed.email.lower()
        except Exception:
            pass
        identity = lookup_identity(email)
        if identity is None:
            flash("No account with that email.", "error")
            return redirect(url_for("auth.login"))
        if identity.get("kind") == "participant" and not identity["obj"].is_active:
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login"))
        if identity.get("kind") == "both":
            user = identity["user"]
            participant = identity["participant"]
            if not verify_password(password, user.password_hash):
                flash("Invalid email or password.", "error")
                return redirect(url_for("auth.login"))
            login_identity(identity)
            db.session.add(
                AuditLog(
                    action="login_dupe_email",
                    details=f"users_id={user.id}, participants_id={participant.id}",
                )
            )
            db.session.commit()
            flash("Signed in as staff account; learner account also exists.", "warning")
            return redirect(url_for("home"))
        obj = identity["obj"]
        if not verify_password(password, obj.password_hash):
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login"))
        login_identity(identity)
        if identity["kind"] == "user":
            return redirect(url_for("home"))
        return redirect(url_for("learner.my_certs"))
    # GET
    if flask_session.get("user_id"):
        return redirect(url_for("home"))
    if flask_session.get("participant_account_id"):
        return redirect(url_for("learner.my_certs"))
    return render_template("auth/login_unified.html")


@bp.route("/forgot-password", methods=["GET", "POST"], endpoint="forgot_password")
def forgot_password():
    if request.method == "POST":
        email_input = request.form.get("email", "")
        try:
            email = validate_email(email_input).email.lower()  # type: ignore
        except Exception:
            email = ""
        target = None
        kind = "user"
        if email:
            target = User.query.filter(func.lower(User.email) == email).first()
            if not target:
                target = ParticipantAccount.query.filter(func.lower(ParticipantAccount.email) == email).first()
                kind = "participant"
        if target:
            serializer = URLSafeTimedSerializer(current_app.secret_key)
            payload = {"kind": kind, "email": email}
            token = serializer.dumps(payload, salt="pwd-reset")
            link = url_for("auth.reset_password", token=token, _external=True)
            res = emailer.send(
                email,
                "Reset your KT CBS password.",
                f"Use this link to reset your password: {link}",
            )
            if not res.get("ok"):
                flask_session["dev_reset_token"] = token
            flash("If we find an account, we'll email a link.", "info")
        return redirect(url_for("auth.forgot_password"))
    token = flask_session.pop("dev_reset_token", None)
    return render_template("forgot_password.html", token=token)


@bp.route("/reset-password", methods=["GET", "POST"], endpoint="reset_password")
def reset_password():
    token = request.values.get("token", "")
    serializer = URLSafeTimedSerializer(current_app.secret_key)
    try:
        data = serializer.loads(token, salt="pwd-reset", max_age=3600)
    except (BadSignature, SignatureExpired):
        flash("Invalid or expired token", "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        pwd = request.form.get("password") or ""
        confirm = request.form.get("password_confirm") or ""
        if not pwd or pwd != confirm:
            flash("Passwords do not match", "error")
            return redirect(url_for("auth.reset_password", token=token))
        if data.get("kind") == "user":
            target = User.query.filter(func.lower(User.email) == data.get("email")).first()
        else:
            target = ParticipantAccount.query.filter(func.lower(ParticipantAccount.email) == data.get("email")).first()
        if not target:
            flash("Account not found", "error")
            return redirect(url_for("auth.forgot_password"))
        target.set_password(pwd)
        db.session.commit()
        flash("Password reset. Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("reset_password.html", token=token)


@bp.route("/logout", methods=["GET", "POST"], endpoint="logout")
def logout():
    flask_session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("auth.login"))


# Optional dependency for email validation
try:  # pragma: no cover
    from email_validator import validate_email  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    def validate_email(email: str):  # type: ignore
        return type("E", (), {"email": email})()
