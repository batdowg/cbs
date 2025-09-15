from __future__ import annotations

import os
from typing import Optional

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
from werkzeug.datastructures import FileStorage

from ..app import db, User
from ..models import Resource, WorkshopType, AuditLog
from ..forms.resource_forms import validate_resource_form
from ..shared.storage import write_atomic
from ..shared.storage_resources import (
    remove_resource_dir,
    resource_fs_dir,
    resource_path_from_value,
    resource_web_url,
    sanitize_filename,
)

bp = Blueprint("settings_resources", __name__, url_prefix="/settings/resources")


def _set_file_metadata(resource: Resource, filename: str, size: Optional[int], content_type: Optional[str]) -> None:
    if hasattr(resource, "file_name"):
        resource.file_name = filename
    if hasattr(resource, "file_size"):
        resource.file_size = size
    if hasattr(resource, "file_content_type"):
        resource.file_content_type = content_type


def _clear_file_metadata(resource: Resource) -> None:
    if hasattr(resource, "file_name"):
        resource.file_name = None
    if hasattr(resource, "file_size"):
        resource.file_size = None
    if hasattr(resource, "file_content_type"):
        resource.file_content_type = None


def _save_document_file(resource: Resource, upload: FileStorage) -> tuple[str, Optional[int], Optional[str], str]:
    filename = sanitize_filename(getattr(upload, "filename", "") or "resource")
    directory = resource_fs_dir(resource.id)
    os.makedirs(directory, mode=0o755, exist_ok=True)
    stream = getattr(upload, "stream", None)
    if stream and hasattr(stream, "seek"):
        try:
            stream.seek(0)
        except Exception:
            pass
    data = upload.read()
    dest_path = os.path.join(directory, filename)
    write_atomic(dest_path, data)
    os.chmod(dest_path, 0o644)
    size = len(data) if isinstance(data, (bytes, bytearray)) else None
    content_type = getattr(upload, "mimetype", None) or getattr(upload, "content_type", None)
    return filename, size, content_type, dest_path


def _remove_previous_file(resource: Resource, previous_value: Optional[str], new_path: str) -> None:
    old_path = resource_path_from_value(resource.id, previous_value)
    if not old_path:
        return
    try:
        if os.path.abspath(old_path) != os.path.abspath(new_path) and os.path.isfile(old_path):
            os.remove(old_path)
    except FileNotFoundError:
        pass


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
    initial_value: Optional[str] = None if rtype == "DOCUMENT" else cleaned["link"]
    res = Resource(
        name=name,
        type=rtype,
        resource_value=initial_value,
        description_html=cleaned["description"],
        active=cleaned["active"],
    )
    res.workshop_types = WorkshopType.query.filter(WorkshopType.id.in_(cleaned["workshop_type_ids"])).all()
    db.session.add(res)
    db.session.flush()
    if rtype == "DOCUMENT":
        file = cleaned["file"]
        if file and getattr(file, "filename", ""):
            filename, size, content_type, _new_path = _save_document_file(res, file)
            res.resource_value = resource_web_url(res.id, filename)
            _set_file_metadata(res, filename, size, content_type)
        else:
            _clear_file_metadata(res)
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
    previous_type = res.type
    previous_value = res.resource_value
    res.name = name
    res.type = rtype
    res.active = cleaned["active"]
    res.description_html = cleaned["description"]
    if rtype == "DOCUMENT":
        file = cleaned["file"]
        if file and getattr(file, "filename", ""):
            filename, size, content_type, new_path = _save_document_file(res, file)
            _remove_previous_file(res, previous_value, new_path)
            res.resource_value = resource_web_url(res.id, filename)
            _set_file_metadata(res, filename, size, content_type)
        elif previous_type != "DOCUMENT":
            res.resource_value = None
            _clear_file_metadata(res)
    else:
        res.resource_value = cleaned["link"]
        if previous_type == "DOCUMENT":
            old_path = resource_path_from_value(res.id, previous_value)
            remove_resource_dir(res.id)
            if old_path and os.path.isfile(old_path):
                try:
                    os.remove(old_path)
                except FileNotFoundError:
                    pass
            _clear_file_metadata(res)
    res.workshop_types = WorkshopType.query.filter(WorkshopType.id.in_(cleaned["workshop_type_ids"])).all()
    db.session.add(AuditLog(user_id=current_user.id, action="resource_update", details=name))
    db.session.commit()
    flash("Resource updated", "success")
    return redirect(url_for("settings_resources.list_resources"))
