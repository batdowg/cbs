from __future__ import annotations

import os
import shutil
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    current_app,
)
from werkzeug.utils import secure_filename

from ..app import db
from ..models import CertificateTemplateSeries, CertificateTemplate
from ..shared.rbac import manage_users_required
from ..shared.languages import get_language_options

bp = Blueprint(
    "settings_cert_templates", __name__, url_prefix="/settings/cert-templates"
)


@bp.get("/")
@manage_users_required
def list_series(current_user):
    series = CertificateTemplateSeries.query.order_by(
        CertificateTemplateSeries.code
    ).all()
    return render_template("settings_cert_templates/list.html", series=series)


@bp.get("/new")
@manage_users_required
def new_series(current_user):
    return render_template("settings_cert_templates/form.html", series=None)


@bp.post("/new")
@manage_users_required
def create_series(current_user):
    code = (request.form.get("code") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    if not code or not name:
        flash("Code and name required", "error")
        return redirect(url_for("settings_cert_templates.new_series"))
    existing = CertificateTemplateSeries.query.filter(
        db.func.lower(CertificateTemplateSeries.code) == code
    ).first()
    if existing:
        flash("Code already exists", "error")
        return redirect(url_for("settings_cert_templates.new_series"))
    series = CertificateTemplateSeries(
        code=code, name=name, is_active=bool(request.form.get("is_active"))
    )
    db.session.add(series)
    db.session.commit()
    flash("Series created", "success")
    return redirect(url_for("settings_cert_templates.list_series"))


@bp.get("/<int:series_id>/edit")
@manage_users_required
def edit_series(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    return render_template("settings_cert_templates/form.html", series=series)


@bp.post("/<int:series_id>/edit")
@manage_users_required
def update_series(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Name required", "error")
        return redirect(
            url_for("settings_cert_templates.edit_series", series_id=series.id)
        )
    series.name = name
    series.is_active = bool(request.form.get("is_active"))
    db.session.commit()
    flash("Series updated", "success")
    return redirect(url_for("settings_cert_templates.list_series"))


@bp.get("/<int:series_id>/templates")
@manage_users_required
def edit_templates(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    languages = get_language_options()
    mapping = {(t.language, t.size): t.filename for t in series.templates}
    badge_mapping = {}
    for t in series.templates:
        if t.badge_filename and t.language not in badge_mapping:
            badge_mapping[t.language] = t.badge_filename
    assets_dir = os.path.join(current_app.root_path, "assets")
    files = sorted([f for f in os.listdir(assets_dir) if f.lower().endswith(".pdf")])
    badge_dir = os.path.join(current_app.root_path, "assets", "badges")
    badges = sorted(
        [
            f
            for f in os.listdir(badge_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
        ]
    )
    return render_template(
        "settings_cert_templates/templates.html",
        series=series,
        languages=languages,
        mapping=mapping,
        files=files,
        badges=badges,
        badge_mapping=badge_mapping,
    )


@bp.post("/<int:series_id>/upload-pdfs")
@manage_users_required
def upload_pdfs(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    files = request.files.getlist("files")
    assets_dir = os.path.join(current_app.root_path, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    max_size = 10 * 1024 * 1024
    uploaded = replaced = skipped = 0
    for f in files:
        filename = secure_filename(f.filename or "")
        if not filename.lower().endswith(".pdf"):
            skipped += 1
            flash(f"Skipped {f.filename}: invalid file type", "error")
            continue
        f.stream.seek(0, os.SEEK_END)
        size = f.stream.tell()
        f.stream.seek(0)
        if size > max_size:
            skipped += 1
            flash(f"Skipped {filename}: file too large", "error")
            continue
        dest = os.path.join(assets_dir, filename)
        action = "replaced" if os.path.exists(dest) else "uploaded"
        f.save(dest)
        current_app.logger.info(
            "[TEMPLATE-PDF-UPLOAD] user=%s file=%s action=%s",
            getattr(current_user, "email", ""),
            filename,
            action,
        )
        if action == "replaced":
            replaced += 1
        else:
            uploaded += 1
    flash(f"Uploaded {uploaded}, replaced {replaced}, skipped {skipped}.", "success")
    return redirect(url_for("settings_cert_templates.edit_templates", series_id=series.id))


@bp.post("/<int:series_id>/upload-badges")
@manage_users_required
def upload_badges(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    files = request.files.getlist("files")
    badge_dir = os.path.join(current_app.root_path, "assets", "badges")
    site_dir = os.path.join(current_app.config.get("SITE_ROOT", "/srv"), "badges")
    os.makedirs(badge_dir, exist_ok=True)
    os.makedirs(site_dir, exist_ok=True)
    max_size = 5 * 1024 * 1024
    uploaded = replaced = skipped = 0
    for f in files:
        filename = secure_filename(f.filename or "")
        if not filename.lower().endswith(".webp"):
            skipped += 1
            flash(f"Skipped {f.filename}: invalid file type", "error")
            continue
        f.stream.seek(0, os.SEEK_END)
        size = f.stream.tell()
        f.stream.seek(0)
        if size > max_size:
            skipped += 1
            flash(f"Skipped {filename}: file too large", "error")
            continue
        dest = os.path.join(badge_dir, filename)
        action = "replaced" if os.path.exists(dest) else "uploaded"
        f.save(dest)
        shutil.copy2(dest, os.path.join(site_dir, filename))
        current_app.logger.info(
            "[BADGE-UPLOAD] user=%s file=%s action=%s",
            getattr(current_user, "email", ""),
            filename,
            action,
        )
        if action == "replaced":
            replaced += 1
        else:
            uploaded += 1
    flash(f"Uploaded {uploaded}, replaced {replaced}, skipped {skipped}.", "success")
    return redirect(url_for("settings_cert_templates.edit_templates", series_id=series.id))


@bp.post("/<int:series_id>/templates")
@manage_users_required
def update_templates(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    languages = get_language_options()
    for code, _ in languages:
        badge_filename = (request.form.get(f"badge_{code}") or "").strip() or None
        for size in ["A4", "LETTER"]:
            key = f"{code}_{size}"
            filename = (request.form.get(key) or "").strip()
            tmpl = CertificateTemplate.query.filter_by(
                series_id=series.id, language=code, size=size
            ).one_or_none()
            if filename:
                if tmpl:
                    tmpl.filename = filename
                    tmpl.badge_filename = badge_filename
                else:
                    db.session.add(
                        CertificateTemplate(
                            series_id=series.id,
                            language=code,
                            size=size,
                            filename=filename,
                            badge_filename=badge_filename,
                        )
                    )
            elif tmpl:
                db.session.delete(tmpl)
    db.session.commit()
    flash("Template mappings updated", "success")
    return redirect(
        url_for("settings_cert_templates.edit_templates", series_id=series.id)
    )
