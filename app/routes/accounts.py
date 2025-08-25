from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from ..app import db
from ..models import ParticipantAccount, Participant, AuditLog
from ..utils.rbac import admin_required

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("/<int:account_id>/password", methods=["GET", "POST"])
@admin_required
def set_account_password(account_id: int, current_user):
    account = db.session.get(ParticipantAccount, account_id)
    if not account:
        abort(404)
    if request.method == "POST":
        pwd = request.form.get("password") or ""
        confirm = request.form.get("password_confirm") or ""
        if not pwd or pwd != confirm:
            flash("Passwords do not match", "error")
            return redirect(
                url_for("accounts.set_account_password", account_id=account.id, next=request.args.get("next"))
            )
        account.set_password(pwd)
        participant = (
            db.session.query(Participant)
            .filter(func.lower(Participant.email) == account.email.lower())
            .first()
        )
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                participant_id=participant.id if participant else None,
                action="password_reset_admin",
                details=f"account_id={account.id}",
            )
        )
        db.session.commit()
        flash("Password updated", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("index"))
    return render_template("account_password.html", account=account)
