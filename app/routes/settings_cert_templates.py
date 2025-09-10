from __future__ import annotations

import os
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    current_app,
    jsonify,
)

from ..app import db
from ..forms.resource_forms import slugify_filename
from ..models import CertificateTemplateSeries, CertificateTemplate
from ..shared.rbac import manage_users_required
from ..shared.languages import get_language_options
from ..shared.storage import ensure_dir

bp = Blueprint(
    "settings_cert_templates", __name__, url_prefix="/settings/cert-templates"
)

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


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


@bp.post("/<int:series_id>/upload-template")
@manage_users_required
def upload_template(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    lang = (request.form.get("language") or "").strip()
    size = (request.form.get("size") or "").strip().upper()
    file = request.files.get("file")
    if size not in {"A4", "LETTER"} or not lang or not file:
        return jsonify({"error": "Invalid input"}), 400
    _, ext = os.path.splitext(file.filename)
    if ext.lower() != ".pdf":
        return jsonify({"error": "PDF required"}), 400
    file.stream.seek(0, os.SEEK_END)
    if file.stream.tell() > MAX_UPLOAD_SIZE:
        return jsonify({"error": "File too large"}), 400
    file.stream.seek(0)
    filename = slugify_filename(os.path.splitext(file.filename)[0], file.filename)
    assets_dir = os.path.join(current_app.root_path, "assets")
    ensure_dir(assets_dir)
    file.save(os.path.join(assets_dir, filename))
    tmpl = CertificateTemplate.query.filter_by(
        series_id=series.id, language=lang, size=size
    ).one_or_none()
    if tmpl:
        tmpl.filename = filename
    else:
        db.session.add(
            CertificateTemplate(
                series_id=series.id,
                language=lang,
                size=size,
                filename=filename,
            )
        )
    db.session.commit()
    current_app.logger.info(
        "[CERT-TEMPLATE-UPLOAD] %s uploaded %s for %s %s",
        getattr(current_user, "email", "?"),
        filename,
        lang,
        size,
    )
    return jsonify({"status": "ok", "filename": filename})


@bp.post("/<int:series_id>/upload-badge")
@manage_users_required
def upload_badge(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    lang = (request.form.get("language") or "").strip()
    file = request.files.get("file")
    if not lang or not file:
        return jsonify({"error": "Invalid input"}), 400
    _, ext = os.path.splitext(file.filename)
    if ext.lower() != ".webp":
        return jsonify({"error": "WEBP required"}), 400
    file.stream.seek(0, os.SEEK_END)
    if file.stream.tell() > MAX_UPLOAD_SIZE:
        return jsonify({"error": "File too large"}), 400
    file.stream.seek(0)
    filename = slugify_filename(os.path.splitext(file.filename)[0], file.filename)
    badge_dir = os.path.join(current_app.root_path, "assets", "badges")
    ensure_dir(badge_dir)
    path_assets = os.path.join(badge_dir, filename)
    file.save(path_assets)
    file.stream.seek(0)
    site_dir = "/srv/badges"
    ensure_dir(site_dir)
    file.save(os.path.join(site_dir, filename))
    for size in ["A4", "LETTER"]:
        tmpl = CertificateTemplate.query.filter_by(
            series_id=series.id, language=lang, size=size
        ).one_or_none()
        if tmpl:
            tmpl.badge_filename = filename
    db.session.commit()
    current_app.logger.info(
        "[BADGE-UPLOAD] %s uploaded %s for %s",
        getattr(current_user, "email", "?"),
        filename,
        lang,
    )
    return jsonify({"status": "ok", "filename": filename})
