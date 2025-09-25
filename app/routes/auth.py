from __future__ import annotations

from flask import (
    Blueprint,
    abort,
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
from ..models import (
    User,
    ParticipantAccount,
    AuditLog,
    PreworkAssignment,
    PreworkEmailLog,
    Session,
)
from ..shared.auth_bridge import lookup_identity, verify_password, login_identity
from ..shared.time import now_utc
from ..shared.names import greeting_name
from .. import emailer
import hashlib
import hmac
import secrets
from datetime import timedelta, timezone
from ..shared.constants import MAGIC_LINK_TTL_DAYS

bp = Blueprint("auth", __name__)


@bp.get("/prework/a/<int:assignment_id>/<token>")
def prework_magic(assignment_id: int, token: str):
    try:
        assignment = db.session.get(PreworkAssignment, assignment_id)
        if not assignment:
            current_app.logger.info(
                f"[AUTH-FAIL] prework assignment={assignment_id} reason=missing"
            )
            return (
                render_template(
                    "prework_magic_error.html",
                    is_staff=bool(flask_session.get("user_id")),
                    assignment=None,
                ),
                404,
            )
        expires = assignment.magic_token_expires
        reason = None
        if not assignment.magic_token_hash or not expires:
            reason = "missing"
        else:
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now_utc():
                reason = "expired"
            else:
                expected = hashlib.sha256(
                    (token + current_app.secret_key).encode()
                ).hexdigest()
                if not hmac.compare_digest(expected, assignment.magic_token_hash):
                    reason = "mismatch"
        if reason:
            current_app.logger.info(
                f"[AUTH-FAIL] prework assignment={assignment_id} reason={reason}"
            )
            return (
                render_template(
                    "prework_magic_error.html",
                    is_staff=bool(flask_session.get("user_id")),
                    assignment=assignment,
                ),
                400,
            )
        flask_session["participant_account_id"] = assignment.participant_account_id
        account = db.session.get(ParticipantAccount, assignment.participant_account_id)
        email = ""
        if account:
            account.last_login = now_utc()
            email = account.email
        assignment.magic_token_hash = None
        assignment.magic_token_expires = now_utc()
        db.session.commit()
        current_app.logger.info(
            f"[AUTH] prework granted assignment={assignment_id} email={email}"
        )
        if account and account.must_change_password:
            flash("Please set a new password to continue.", "error")
            return redirect(url_for("learner.profile") + "#password")
        return redirect(url_for("learner.prework_form", assignment_id=assignment_id))
    except Exception:  # pragma: no cover - defensive
        current_app.logger.info(
            f"[AUTH-FAIL] prework assignment={assignment_id} reason=error"
        )
        return (
            render_template(
                "prework_magic_error.html",
                is_staff=bool(flask_session.get("user_id")),
                assignment=None,
            ),
            400,
        )


@bp.post("/prework/a/<int:assignment_id>/resend")
def prework_magic_resend(assignment_id: int):
    if not flask_session.get("user_id"):
        abort(403)
    assignment = db.session.get(PreworkAssignment, assignment_id)
    if not assignment:
        abort(404)
    account = assignment.participant_account
    token = secrets.token_urlsafe(16)
    assignment.magic_token_hash = hashlib.sha256(
        (token + current_app.secret_key).encode()
    ).hexdigest()
    assignment.magic_token_expires = now_utc() + timedelta(
        days=MAGIC_LINK_TTL_DAYS
    )
    db.session.flush()
    link = url_for(
        "auth.prework_magic",
        assignment_id=assignment.id,
        token=token,
        _external=True,
        _scheme="https",
    )
    sess = assignment.session
    recipient_name = greeting_name(account=account)
    subject = f"Prework for Workshop: {sess.title}"
    body = render_template(
        "email/prework.txt",
        session=sess,
        assignment=assignment,
        link=link,
        account=account,
        greeting_name=recipient_name,
        temp_password=None,
    )
    html_body = render_template(
        "email/prework.html",
        session=sess,
        assignment=assignment,
        link=link,
        account=account,
        greeting_name=recipient_name,
        temp_password=None,
    )
    try:
        res = emailer.send(account.email, subject, body, html=html_body)
    except Exception as e:  # pragma: no cover - defensive
        res = {"ok": False, "detail": str(e)}
    if res.get("ok"):
        assignment.status = "SENT"
        assignment.sent_at = now_utc()
        db.session.add(
            PreworkEmailLog(
                assignment_id=assignment.id,
                to_email=account.email,
                subject=subject,
            )
        )
        current_app.logger.info(
            f"[MAIL-OUT] prework session={assignment.session_id} pa={account.id} to={account.email} subject=\"{subject}\""
        )
    else:
        current_app.logger.info(
            f"[MAIL-FAIL] prework session={assignment.session_id} pa={account.id} to={account.email} error=\"{res.get('detail')}\""
        )
    db.session.commit()
    flash("Prework link sent.", "info")
    return redirect(url_for("sessions.session_prework", session_id=assignment.session_id))


@bp.get("/account/a/<int:account_id>/<token>")
def account_magic(account_id: int, token: str):
    account = db.session.get(ParticipantAccount, account_id)
    reason = None
    if not account or not account.login_magic_hash or not account.login_magic_expires:
        reason = "missing"
    else:
        expires = account.login_magic_expires
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now_utc():
            reason = "expired"
        else:
            expected = hashlib.sha256(
                (token + current_app.secret_key).encode()
            ).hexdigest()
            if not hmac.compare_digest(expected, account.login_magic_hash):
                reason = "mismatch"
    if reason:
        current_app.logger.info(
            f"[AUTH-FAIL] account participant_account_id={account_id} reason={reason}"
        )
        abort(400)
    flask_session["participant_account_id"] = account.id
    account.last_login = now_utc()
    account.login_magic_hash = None
    account.login_magic_expires = now_utc()
    db.session.commit()
    current_app.logger.info(
        f"[AUTH] account granted participant_account_id={account.id}"
    )
    if account.must_change_password:
        flash("Please set a new password to continue.", "error")
        return redirect(url_for("learner.profile") + "#password")
    is_csa = (
        db.session.query(Session.id)
        .filter(Session.csa_account_id == account.id)
        .first()
        is not None
    )
    target = "csa.my_sessions" if is_csa else "learner.my_workshops"
    resp = redirect(url_for(target))
    if not request.cookies.get("active_view"):
        resp.set_cookie("active_view", "CSA" if is_csa else "LEARNER", samesite="Lax")
    return resp


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
            resp = redirect(url_for("home"))
            if not request.cookies.get("active_view"):
                resp.set_cookie("active_view", user.preferred_view or "ADMIN", samesite="Lax")
            return resp
        obj = identity["obj"]
        if not verify_password(password, obj.password_hash):
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login"))
        login_identity(identity)
        if identity["kind"] == "user":
            resp = redirect(url_for("home"))
            if not request.cookies.get("active_view"):
                resp.set_cookie("active_view", obj.preferred_view or "ADMIN", samesite="Lax")
            return resp
        account = identity["obj"]
        if account.must_change_password:
            flash("Please set a new password to continue.", "error")
            return redirect(url_for("learner.profile") + "#password")
        is_csa = (
            db.session.query(Session.id)
            .filter(Session.csa_account_id == account.id)
            .first()
            is not None
        )
        target = "csa.my_sessions" if is_csa else "learner.my_workshops"
        resp = redirect(url_for(target))
        if not request.cookies.get("active_view"):
            resp.set_cookie(
                "active_view", "CSA" if is_csa else "LEARNER", samesite="Lax"
            )
        return resp
    # GET
    if flask_session.get("user_id"):
        return redirect(url_for("home"))
    if flask_session.get("participant_account_id"):
        account_id = flask_session.get("participant_account_id")
        is_csa = (
            db.session.query(Session.id)
            .filter(Session.csa_account_id == account_id)
            .first()
            is not None
        )
        if is_csa:
            return redirect(url_for("csa.my_sessions"))
        return redirect(url_for("learner.my_workshops"))
    dev_token = flask_session.pop("dev_reset_token", None)
    forgot_flag = request.args.get("forgot", "").lower()
    forgot_open = forgot_flag in {"1", "true", "yes"}
    return render_template(
        "auth/login_unified.html",
        forgot_open=forgot_open,
        dev_reset_token=dev_token,
    )


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
        return redirect(url_for("auth.login", forgot=1, email=email_input))
    forgot_param = request.args.get("forgot") or "1"
    email_param = request.args.get("email")
    target_args = {"forgot": forgot_param}
    if email_param:
        target_args["email"] = email_param
    return redirect(url_for("auth.login", **target_args))


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
