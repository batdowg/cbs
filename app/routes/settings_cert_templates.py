from __future__ import annotations

import os
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, current_app

from ..app import db
from ..models import CertificateTemplateSeries, CertificateTemplate
from ..utils.rbac import manage_users_required
from ..utils.languages import get_language_options

bp = Blueprint("settings_cert_templates", __name__, url_prefix="/settings/cert-templates")


@bp.get("/")
@manage_users_required
def list_series(current_user):
    series = CertificateTemplateSeries.query.order_by(CertificateTemplateSeries.code).all()
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
    existing = CertificateTemplateSeries.query.filter(db.func.lower(CertificateTemplateSeries.code) == code).first()
    if existing:
        flash("Code already exists", "error")
        return redirect(url_for("settings_cert_templates.new_series"))
    series = CertificateTemplateSeries(code=code, name=name, is_active=bool(request.form.get("is_active")))
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
        return redirect(url_for("settings_cert_templates.edit_series", series_id=series.id))
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
    assets_dir = os.path.join(current_app.root_path, "assets")
    files = sorted([f for f in os.listdir(assets_dir) if f.lower().endswith(".pdf")])
    return render_template(
        "settings_cert_templates/templates.html",
        series=series,
        languages=languages,
        mapping=mapping,
        files=files,
    )


@bp.post("/<int:series_id>/templates")
@manage_users_required
def update_templates(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    languages = get_language_options()
    for code, _ in languages:
        for size in ["A4", "LETTER"]:
            key = f"{code}_{size}"
            filename = (request.form.get(key) or "").strip()
            tmpl = CertificateTemplate.query.filter_by(series_id=series.id, language=code, size=size).one_or_none()
            if filename:
                if tmpl:
                    tmpl.filename = filename
                else:
                    db.session.add(CertificateTemplate(series_id=series.id, language=code, size=size, filename=filename))
            elif tmpl:
                db.session.delete(tmpl)
    db.session.commit()
    flash("Template mappings updated", "success")
    return redirect(url_for("settings_cert_templates.edit_templates", series_id=series.id))
