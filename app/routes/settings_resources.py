from __future__ import annotations

import os

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func

from ..app import db, User
from ..models import Resource, WorkshopType, AuditLog
from ..forms.resource_forms import slugify_filename, validate_resource_form
from ..shared.storage import ensure_dir

bp = Blueprint("settings_resources", __name__, url_prefix="/settings/resources")


def _current_user(require_edit: bool = False) -> "User | Response":
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))
    user = db.session.get(User, user_id)
    if not user:
        abort(403)
    can_view = (
        user.is_app_admin
        or user.is_admin
        or user.is_kt_delivery
        or user.is_kt_facilitator
        or user.is_kt_contractor
    )
    if not can_view:
        abort(403)
    if require_edit and not (user.is_app_admin or user.is_admin or user.is_kt_delivery):
        abort(403)
    return user


@bp.get("/")
def list_resources():
    current_user = _current_user()
    if isinstance(current_user, Response):
        return current_user
    resources = Resource.query.order_by(Resource.name).all()
    return render_template(
        "settings_resources/list.html",
        resources=resources,
        active_nav="settings",
        active_section="resources",
    )


@bp.get("/new")
def new_resource():
    current_user = _current_user(require_edit=True)
    if isinstance(current_user, Response):
        return current_user
    workshop_types = WorkshopType.query.order_by(WorkshopType.name).all()
    return render_template(
        "settings_resources/form.html",
        resource=None,
        workshop_types=workshop_types,
        active_nav="settings",
        active_section="resources",
    )


@bp.post("/new")
def create_resource():
    current_user = _current_user(require_edit=True)
    if isinstance(current_user, Response):
        return current_user
    errors, cleaned = validate_resource_form(request.form, request.files, require_file=True if (request.form.get("type") or "").upper() == "DOCUMENT" else False)
    name = cleaned.get("name")
    if Resource.query.filter(func.lower(Resource.name) == name.lower(), Resource.active == True).first():
        errors.append("Name must be unique")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("settings_resources.new_resource"))
    rtype = cleaned["type"]
    if rtype == "DOCUMENT":
        file = cleaned["file"]
        filename = slugify_filename(name, file.filename)
        ensure_dir("/srv/resources")
        file.save(os.path.join("/srv/resources", filename))
        resource_value = filename
    else:
        resource_value = cleaned["link"]
    res = Resource(
        name=name,
        type=rtype,
        resource_value=resource_value,
        active=cleaned["active"],
    )
    res.workshop_types = WorkshopType.query.filter(WorkshopType.id.in_(cleaned["workshop_type_ids"])).all()
    db.session.add(res)
    db.session.add(AuditLog(user_id=current_user.id, action="resource_create", details=name))
    db.session.commit()
    flash("Resource created", "success")
    return redirect(url_for("settings_resources.list_resources"))


@bp.get("/<int:res_id>/edit")
def edit_resource(res_id: int):
    current_user = _current_user(require_edit=True)
    if isinstance(current_user, Response):
        return current_user
    res = db.session.get(Resource, res_id)
    if not res:
        abort(404)
    workshop_types = WorkshopType.query.order_by(WorkshopType.name).all()
    return render_template(
        "settings_resources/form.html",
        resource=res,
        workshop_types=workshop_types,
        active_nav="settings",
        active_section="resources",
    )


@bp.post("/<int:res_id>/edit")
def update_resource(res_id: int):
    current_user = _current_user(require_edit=True)
    if isinstance(current_user, Response):
        return current_user
    res = db.session.get(Resource, res_id)
    if not res:
        abort(404)
    errors, cleaned = validate_resource_form(request.form, request.files)
    name = cleaned.get("name")
    existing = (
        Resource.query.filter(
            func.lower(Resource.name) == name.lower(),
            Resource.id != res.id,
            Resource.active == True,
        ).first()
    )
    if existing:
        errors.append("Name must be unique")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("settings_resources.edit_resource", res_id=res_id))
    rtype = cleaned["type"]
    res.name = name
    res.type = rtype
    res.active = cleaned["active"]
    if rtype == "DOCUMENT":
        file = cleaned["file"]
        if file and getattr(file, "filename", ""):
            filename = slugify_filename(name, file.filename)
            ensure_dir("/srv/resources")
            file.save(os.path.join("/srv/resources", filename))
            res.resource_value = filename
    else:
        res.resource_value = cleaned["link"]
    res.workshop_types = WorkshopType.query.filter(WorkshopType.id.in_(cleaned["workshop_type_ids"])).all()
    db.session.add(AuditLog(user_id=current_user.id, action="resource_update", details=name))
    db.session.commit()
    flash("Resource updated", "success")
    return redirect(url_for("settings_resources.list_resources"))
