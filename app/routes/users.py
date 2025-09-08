from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import or_, func

from ..app import db, User
from ..models import AuditLog, UserAuditLog
from ..constants import (
    ROLE_ATTRS,
    SYS_ADMIN,
    PERMISSIONS_MATRIX,
    ROLES_MATRIX_VERSION,
)
from ..utils.acl import validate_role_combo, can_demote_to_contractor
from ..utils.rbac import manage_users_required


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
    return ",".join(roles)


@bp.get("/")
@manage_users_required
def list_users(current_user):
    q = (request.args.get("q") or "").strip()
    region = request.args.get("region") or ""
    query = User.query
    if region in ["NA", "EU", "SEA", "Other"]:
        query = query.filter(User.region == region)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                db.func.lower(User.email).like(like),
                db.func.lower(User.full_name).like(like),
            )
        )
    users = query.order_by(User.created_at.desc()).all()
    return render_template(
        "users/list.html",
        users=users,
        q=q,
        region=region,
        matrix=PERMISSIONS_MATRIX,
        version=ROLES_MATRIX_VERSION,
    )


@bp.post("/bulk-update")
@manage_users_required
def bulk_update(current_user):
    users = User.query.order_by(User.id).all()
    updated = 0
    for user in users:
        orig = _roles_str(user)
        role_names = []
        for name, attr in ROLE_ATTRS.items():
            key = f"{attr}_{user.id}"
            if request.form.get(key):
                if name == SYS_ADMIN and not current_user.is_app_admin:
                    continue
                role_names.append(name)
        try:
            validate_role_combo(role_names)
        except ValueError:
            flash("Invalid role combination", "error")
            return redirect(url_for("users.list_users"))
        for name, attr in ROLE_ATTRS.items():
            setattr(user, attr, name in role_names)
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
@manage_users_required
def new_user(current_user):
    return render_template("users/form.html", user=None)


@bp.post("/new")
@manage_users_required
def create_user(current_user):
    email = (request.form.get("email") or "").lower()
    if not email:
        flash("Email required", "error")
        return redirect(url_for("users.new_user"))
    if User.query.filter(db.func.lower(User.email) == email).first():
        flash("Email already exists", "error")
        return redirect(url_for("users.new_user"))
    role_names = []
    for name, attr in ROLE_ATTRS.items():
        if request.form.get(attr):
            if name == SYS_ADMIN and not current_user.is_app_admin:
                continue
            role_names.append(name)
    try:
        validate_role_combo(role_names)
    except ValueError:
        flash("Invalid role combination", "error")
        return redirect(url_for("users.new_user"))
    region = request.form.get("region")
    if region not in ["NA", "EU", "SEA", "Other"]:
        flash("Region required", "error")
        return redirect(url_for("users.new_user"))
    user = User(
        email=email,
        full_name=request.form.get("full_name"),
        title=request.form.get("title"),
        region=region,
    )
    for name, attr in ROLE_ATTRS.items():
        setattr(user, attr, name in role_names)
    pwd = confirm = ""
    if current_user.is_app_admin:
        pwd = request.form.get("password") or ""
        confirm = request.form.get("password_confirm") or ""
        if pwd or confirm:
            if pwd != confirm:
                flash("Passwords do not match", "error")
                return redirect(url_for("users.new_user"))
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
@manage_users_required
def edit_user(user_id: int, current_user):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    can_demote = can_demote_to_contractor(current_user, user)
    return render_template("users/edit.html", user=user, can_demote=can_demote)


@bp.post("/<int:user_id>/edit")
@manage_users_required
def update_user(user_id: int, current_user):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    full_name = (request.form.get("full_name") or "").strip()
    title_val = request.form.get("title")
    title = title_val.strip() if title_val is not None else (user.title or "")
    if not full_name or len(full_name) > 120:
        flash("Full name required", "error")
        return redirect(url_for("users.edit_user", user_id=user.id))
    region = request.form.get("region")
    if region not in ["NA", "EU", "SEA", "Other"]:
        flash("Region required", "error")
        return redirect(url_for("users.edit_user", user_id=user.id))

    changes: list[tuple[str, str | None, str | None]] = []
    if user.full_name != full_name:
        changes.append(("full_name", user.full_name, full_name))
        user.full_name = full_name
    if title_val is not None and user.title != title:
        changes.append(("title", user.title, title))
        user.title = title
    if user.region != region:
        changes.append(("region", user.region, region))
        user.region = region

    for field, old, new in changes:
        db.session.add(
            UserAuditLog(
                actor_user_id=current_user.id,
                target_user_id=user.id,
                field=field,
                old_value=old,
                new_value=new,
            )
        )

    if current_user.is_app_admin:
        pwd = request.form.get("password") or ""
        confirm = request.form.get("password_confirm") or ""
        if pwd or confirm:
            if pwd != confirm:
                flash("Passwords do not match", "error")
                return redirect(url_for("users.edit_user", user_id=user.id))
            user.set_password(pwd)
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    action="password_reset_admin",
                    details=f"user_id={user.id}",
                )
            )

    db.session.commit()
    if changes or (pwd or confirm):
        flash("User updated.", "success")
    else:
        flash("No changes.", "info")
    return redirect(url_for("users.list_users"))



@bp.post("/<int:user_id>/demote-contractor")
@manage_users_required
def demote_contractor(user_id: int, current_user):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if not can_demote_to_contractor(current_user, user):
        abort(403)
    if user.is_admin:
        remaining = User.query.filter(User.id != user.id, User.is_admin == True).count()
        if remaining == 0:
            flash("Cannot remove the last Admin/Sys Admin", "error")
            return redirect(url_for("users.edit_user", user_id=user.id))
    from ..utils.accounts import demote_user_to_contractor

    demote_user_to_contractor(user, current_user)
    db.session.commit()
    flash("User converted to contractor", "success")
    return redirect(url_for("users.edit_user", user_id=user.id))

