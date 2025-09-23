from __future__ import annotations

import os
import shutil
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    current_app,
)
from werkzeug.utils import secure_filename

from ..app import db
from ..models import CertificateTemplateSeries, CertificateTemplate
from ..shared.rbac import manage_users_required
from ..shared.languages import get_language_options
from ..shared.certificates_layout import (
    DETAIL_SIDES,
    DETAIL_SIZE_MAX_PERCENT,
    DETAIL_SIZE_MIN_PERCENT,
    DETAIL_VARIABLES,
    PAGE_HEIGHT_MM,
    filter_detail_variables,
    filter_font_codes,
    get_default_size_layout,
    get_font_options,
    sanitize_series_layout,
)
from ..services.certificates_preview import (
    generate_preview,
    sanitize_layout_for_preview,
)

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
    layout = sanitize_series_layout(series.layout_config)
    language_lookup = {code: name for code, name in languages}
    preview_languages = {"A4": [], "LETTER": []}
    for size in ["A4", "LETTER"]:
        for code, _ in languages:
            if mapping.get((code, size)):
                preview_languages[size].append((code, language_lookup.get(code, code)))
    default_preview_language: dict[str, str | None] = {}
    for size in ["A4", "LETTER"]:
        codes = preview_languages[size]
        preferred = next((code for code, _ in codes if code == "en"), None)
        if not preferred and codes:
            preferred = codes[0][0]
        default_preview_language[size] = preferred
    return render_template(
        "settings_cert_templates/templates.html",
        series=series,
        languages=languages,
        mapping=mapping,
        files=files,
        badges=badges,
        badge_mapping=badge_mapping,
        layout=layout,
        font_options=get_font_options(),
        detail_variables=DETAIL_VARIABLES,
        detail_sides=DETAIL_SIDES,
        detail_size_min=DETAIL_SIZE_MIN_PERCENT,
        detail_size_max=DETAIL_SIZE_MAX_PERCENT,
        preview_languages=preview_languages,
        default_preview_language=default_preview_language,
    )


@bp.post("/<int:series_id>/preview")
@manage_users_required
def preview_series(series_id: int, current_user):
    series = db.session.get(CertificateTemplateSeries, series_id)
    if not series:
        abort(404)
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "Invalid request payload."}), 400
    token = payload.get("csrf_token")
    if not token or token != session.get("_csrf_token"):
        return jsonify({"error": "Invalid CSRF token."}), 400
    size = str(payload.get("paper_size", "")).upper()
    if size not in {"A4", "LETTER"}:
        return jsonify({"error": "Invalid paper size."}), 400
    language = str(payload.get("language") or "")
    configured_languages = {
        tmpl.language
        for tmpl in series.templates
        if tmpl.size == size
    }
    if language not in configured_languages:
        return jsonify({"error": "Language is not configured for this paper size."}), 400
    override_layout = payload.get("layout") if isinstance(payload, dict) else None
    sanitized_layout = sanitize_layout_for_preview(
        series,
        size=size,
        override=override_layout if isinstance(override_layout, dict) else None,
    )
    try:
        preview = generate_preview(
            series,
            language=language,
            size=size,
            layout=sanitized_layout,
        )
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Certificate preview failed")
        return jsonify({"error": "Failed to generate preview."}), 500
    return jsonify(
        {
            "image": f"data:image/png;base64,{preview.image_base64}",
            "warnings": preview.warnings,
        }
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
    layout_errors: list[str] = []
    new_layout: dict[str, dict] = {}
    for size in ["A4", "LETTER"]:
        defaults = get_default_size_layout(size)
        size_layout: dict[str, object] = {}
        for key in ["name", "workshop", "date"]:
            font_val = request.form.get(f"layout_{size}_{key}_font") or defaults[key]["font"]
            filtered_font = filter_font_codes([font_val])
            if filtered_font:
                font = filtered_font[0]
            else:
                font = defaults[key]["font"]
            y_raw = (request.form.get(f"layout_{size}_{key}_y") or "").strip()
            if y_raw:
                try:
                    y_val = float(y_raw)
                except ValueError:
                    layout_errors.append(f"{size} {key.title()} Y position must be a number")
                    y_val = defaults[key]["y_mm"]
                else:
                    max_y = PAGE_HEIGHT_MM.get(size, 300)
                    if y_val < 0 or y_val > max_y:
                        layout_errors.append(
                            f"{size} {key.title()} Y position must be between 0 and {max_y}"
                        )
                        y_val = defaults[key]["y_mm"]
            else:
                y_val = defaults[key]["y_mm"]
            size_layout[key] = {"font": font, "y_mm": y_val}
        enabled = bool(request.form.get(f"layout_{size}_details_enabled"))
        side = (request.form.get(f"layout_{size}_details_side") or "LEFT").upper()
        if side not in DETAIL_SIDES:
            side = "LEFT"
        variables = filter_detail_variables(
            request.form.getlist(f"layout_{size}_details_variables")
        )
        size_default = defaults["details"]["size_percent"]
        size_raw = (request.form.get(f"layout_{size}_details_size_percent") or "").strip()
        size_percent = size_default
        if size_raw:
            try:
                parsed = int(size_raw)
            except ValueError:
                layout_errors.append(
                    f"{size} Details Size % must be a whole number"
                )
            else:
                if not (
                    DETAIL_SIZE_MIN_PERCENT
                    <= parsed
                    <= DETAIL_SIZE_MAX_PERCENT
                ):
                    layout_errors.append(
                        f"{size} Details Size % must be between {DETAIL_SIZE_MIN_PERCENT} and {DETAIL_SIZE_MAX_PERCENT}"
                    )
                else:
                    size_percent = parsed
        size_layout["details"] = {
            "enabled": enabled,
            "side": side,
            "variables": variables,
            "size_percent": size_percent,
        }
        new_layout[size] = size_layout

    if layout_errors:
        for msg in layout_errors:
            flash(msg, "error")
        return redirect(url_for("settings_cert_templates.edit_templates", series_id=series.id))

    series.layout_config = new_layout
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
