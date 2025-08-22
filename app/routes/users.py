from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..app import db, User
from ..models import AuditLog
from ..utils.rbac import admin_required


bp = Blueprint("users", __name__, url_prefix="/users")


def _roles_str(user: User) -> str:
    roles: list[str] = []
    if user.is_app_admin:
        roles.append("app_admin")
    if user.is_admin:
        roles.append("admin")
    if user.is_kcrm:
        roles.append("kcrm")
    if user.is_kt_delivery:
        roles.append("kt_delivery")
    if user.is_kt_contractor:
        roles.append("kt_contractor")
    if user.is_kt_staff:
        roles.append("kt_staff")
    return ",".join(roles)


@bp.get("/")
@admin_required
def list_users(current_user):
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("users/list.html", users=users)


@bp.post("/bulk-update")
@admin_required
def bulk_update(current_user):
    users = User.query.order_by(User.id).all()
    updated = 0
    for user in users:
        orig = _roles_str(user)
        if current_user.is_app_admin:
            user.is_app_admin = bool(request.form.get(f"is_app_admin_{user.id}"))
        user.is_admin = bool(request.form.get(f"is_admin_{user.id}"))
        user.is_kcrm = bool(request.form.get(f"is_kcrm_{user.id}"))
        user.is_kt_delivery = bool(request.form.get(f"is_kt_delivery_{user.id}"))
        user.is_kt_contractor = bool(request.form.get(f"is_kt_contractor_{user.id}"))
        new_roles = _roles_str(user)
        if new_roles != orig:
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    action="user_update",
                    details=f"user_id={user.id} roles={new_roles}",
                )
            )
            updated += 1
    db.session.commit()
    flash(f"Updated {updated} users", "success")
    return redirect(url_for("users.list_users"))


@bp.get("/new")
@admin_required
def new_user(current_user):
    return render_template("users/form.html", user=None)


@bp.post("/new")
@admin_required
def create_user(current_user):
    email = (request.form.get("email") or "").lower()
    if not email:
        flash("Email required", "error")
        return redirect(url_for("users.new_user"))
    if User.query.filter(db.func.lower(User.email) == email).first():
        flash("Email already exists", "error")
        return redirect(url_for("users.new_user"))
    region = request.form.get("region")
    if region not in ["NA", "EU", "SEA", "Other"]:
        flash("Region required", "error")
        return redirect(url_for("users.new_user"))
    user = User(
        email=email,
        full_name=request.form.get("full_name"),
        region=region,
        is_app_admin=bool(request.form.get("is_app_admin")) if current_user.is_app_admin else False,
        is_admin=bool(request.form.get("is_admin")),
        is_kcrm=bool(request.form.get("is_kcrm")),
        is_kt_delivery=bool(request.form.get("is_kt_delivery")),
        is_kt_contractor=bool(request.form.get("is_kt_contractor")),
        is_kt_staff=bool(request.form.get("is_kt_staff")),
    )
    pwd = request.form.get("password") or ""
    if pwd:
        user.set_password(pwd)
    db.session.add(user)
    db.session.flush()
    db.session.add(
        AuditLog(
            user_id=current_user.id,
            action="user_create",
            details=f"email={user.email} roles={_roles_str(user)}",
        )
    )
    db.session.commit()
    flash("User created", "success")
    return redirect(url_for("users.list_users"))


@bp.get("/<int:user_id>/edit")
@admin_required
def edit_user(user_id: int, current_user):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    return render_template("users/form.html", user=user)


@bp.post("/<int:user_id>/edit")
@admin_required
def update_user(user_id: int, current_user):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    user.full_name = request.form.get("full_name")
    region = request.form.get("region")
    if region not in ["NA", "EU", "SEA", "Other"]:
        flash("Region required", "error")
        return redirect(url_for("users.edit_user", user_id=user.id))
    user.region = region
    if current_user.is_app_admin:
        user.is_app_admin = bool(request.form.get("is_app_admin"))
    user.is_admin = bool(request.form.get("is_admin"))
    user.is_kcrm = bool(request.form.get("is_kcrm"))
    user.is_kt_delivery = bool(request.form.get("is_kt_delivery"))
    user.is_kt_contractor = bool(request.form.get("is_kt_contractor"))
    user.is_kt_staff = bool(request.form.get("is_kt_staff"))
    pwd = request.form.get("password") or ""
    if pwd:
        user.set_password(pwd)
    db.session.add(
        AuditLog(
            user_id=current_user.id,
            action="user_update",
            details=f"user_id={user.id} roles={_roles_str(user)}",
        )
    )
    db.session.commit()
    flash("User updated", "success")
    return redirect(url_for("users.list_users"))

