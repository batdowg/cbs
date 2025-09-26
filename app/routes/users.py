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
from ..shared.constants import ROLE_ATTRS, SYS_ADMIN
from ..shared.acl import validate_role_combo, can_demote_to_contractor
from ..shared.rbac import manage_users_required
from ..shared.names import combine_first_last, split_full_name


bp = Blueprint("users", __name__, url_prefix="/users")


def _roles_str(user: User) -> str:
    roles: list[str] = []
    if user.is_app_admin:
        roles.append("app_admin")
    if user.is_admin:
        roles.append("admin")
    if user.is_kcrm:
        roles.append("kcrm")
    if getattr(user, "is_certificate_manager", False):
        roles.append("certificate_manager")
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
                db.func.lower(User.first_name).like(like),
                db.func.lower(User.last_name).like(like),
            )
        )
    users = (
        query.order_by(
            db.func.lower(User.last_name).nullslast(),
            db.func.lower(User.first_name).nullslast(),
            db.func.lower(User.full_name).nullslast(),
            User.email,
        ).all()
    )
    return render_template(
        "users/list.html", users=users, q=q, region=region
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
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    if not first_name or not last_name:
        flash("First and last name required", "error")
        return redirect(url_for("users.new_user"))
    full_name_value = combine_first_last(first_name, last_name)
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name_value or email,
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
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    if not first_name or not last_name:
        flash("First and last name required", "error")
        return redirect(url_for("users.edit_user", user_id=user.id))
    full_name = combine_first_last(first_name, last_name)
    if not full_name:
        flash("Full name required", "error")
        return redirect(url_for("users.edit_user", user_id=user.id))
    if len(full_name) > 255:
        flash("Full name too long", "error")
        return redirect(url_for("users.edit_user", user_id=user.id))
    title_val = request.form.get("title")
    title = title_val.strip() if title_val is not None else (user.title or "")
    region = request.form.get("region")
    if region not in ["NA", "EU", "SEA", "Other"]:
        flash("Region required", "error")
        return redirect(url_for("users.edit_user", user_id=user.id))

    changes: list[tuple[str, str | None, str | None]] = []
    if user.first_name != first_name:
        changes.append(("first_name", user.first_name, first_name))
        user.first_name = first_name
    if user.last_name != last_name:
        changes.append(("last_name", user.last_name, last_name))
        user.last_name = last_name
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
    from ..shared.accounts import demote_user_to_contractor

    demote_user_to_contractor(user, current_user)
    db.session.commit()
    flash("User converted to contractor", "success")
    return redirect(url_for("users.edit_user", user_id=user.id))

