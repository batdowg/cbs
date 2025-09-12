import os

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..app import db
from ..emailer import send
from ..models import ProcessorAssignment, Settings, User
from ..shared.rbac import app_admin_required
from ..shared.regions import get_region_options

bp = Blueprint("settings_mail", __name__)


@bp.route("/mail-settings", methods=["GET", "POST"])
@app_admin_required
def settings(current_user):
    settings = Settings.get()
    if not settings:
        settings = Settings(
            id=1,
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=os.getenv("SMTP_PORT", 0),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_from_default=os.getenv(
                "SMTP_FROM_DEFAULT", "certificates@kepner-tregoe.com"
            ),
            smtp_from_name=os.getenv("SMTP_FROM_NAME", ""),
            use_tls=True,
            use_ssl=False,
        )
    if request.method == "POST":
        settings.smtp_host = request.form.get("smtp_host", "")
        settings.smtp_port = int(request.form.get("smtp_port") or 0)
        settings.smtp_user = request.form.get("smtp_user", "")
        settings.smtp_from_default = request.form.get("smtp_from_default", "")
        settings.smtp_from_name = request.form.get("smtp_from_name", "")
        pwd = request.form.get("smtp_pass", "")
        if pwd:
            settings.set_smtp_pass(pwd)
        settings.use_tls = bool(request.form.get("use_tls"))
        settings.use_ssl = bool(request.form.get("use_ssl"))
        db.session.merge(settings)
        db.session.commit()
        flash("Saved")
        return redirect(url_for("settings_mail.settings"))
    # build mapping of (region, processing_type) -> [User]
    assignments: dict[tuple[str, str], list[User]] = {}
    rows = (
        ProcessorAssignment.query.join(User)
        .order_by(
            ProcessorAssignment.region,
            ProcessorAssignment.processing_type,
            User.full_name,
        )
        .all()
    )
    for row in rows:
        assignments.setdefault((row.region, row.processing_type), []).append(
            row.user
        )
    users = User.query.order_by(User.full_name).all()
    return render_template(
        "settings_mail.html",
        settings=settings,
        regions=get_region_options(),
        processing_types=["Digital", "Physical", "Simulation"],
        assignments=assignments,
        users=users,
    )


@bp.post("/mail-settings/test")
@app_admin_required
def test_send(current_user):
    res = send(current_user.email, "CBS test email", "This is a test email.")
    if res.get("ok"):
        flash("Test email sent", "success")
    else:
        flash(f"Error: {res.get('detail')}", "error")
    return redirect(url_for("settings_mail.settings"))


@bp.post("/mail-settings/processors")
@app_admin_required
def save_processors(current_user):
    regions = [code for code, _ in get_region_options()]
    types = ["Digital", "Physical", "Simulation"]
    for region in regions:
        for ptype in types:
            key = f"{region}-{ptype}"
            ids = [int(x) for x in request.form.getlist(key) if x]
            db.session.query(ProcessorAssignment).filter_by(
                region=region, processing_type=ptype
            ).delete()
            for uid in ids:
                db.session.add(
                    ProcessorAssignment(
                        region=region, processing_type=ptype, user_id=uid
                    )
                )
    db.session.commit()
    flash("Processors updated", "success")
    return redirect(url_for("settings_mail.settings"))
