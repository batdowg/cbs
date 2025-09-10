from __future__ import annotations

import os

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..app import db
from ..models import BadgeImage
from ..shared.badges import slug_for_badge
from ..shared.languages import get_language_options
from ..shared.rbac import admin_required

bp = Blueprint("settings_badges", __name__, url_prefix="/settings/badges")


def _sync_badges_from_assets() -> None:
    asset_dir = os.path.join(current_app.root_path, "assets", "badges")
    if not os.path.isdir(asset_dir):
        return
    for filename in os.listdir(asset_dir):
        if not filename.lower().endswith((".webp", ".png")):
            continue
        existing = BadgeImage.query.filter_by(filename=filename).first()
        if existing:
            continue
        name = os.path.splitext(filename)[0]
        badge = BadgeImage(name=name.title(), language="en", filename=filename)
        db.session.add(badge)
    db.session.commit()


@bp.get("/")
@admin_required
def list_badges(current_user):
    _sync_badges_from_assets()
    badges = BadgeImage.query.order_by(BadgeImage.name).all()
    return render_template("settings_badges/list.html", badges=badges)


@bp.get("/<int:badge_id>/edit")
@admin_required
def edit_badge(badge_id: int, current_user):
    badge = db.session.get(BadgeImage, badge_id)
    if not badge:
        abort(404)
    return render_template(
        "settings_badges/form.html",
        badge=badge,
        language_options=get_language_options(),
    )


@bp.post("/<int:badge_id>/edit")
@admin_required
def update_badge(badge_id: int, current_user):
    badge = db.session.get(BadgeImage, badge_id)
    if not badge:
        abort(404)
    name = (request.form.get("name") or "").strip()
    language = request.form.get("language") or "en"
    if not name:
        flash("Name required", "error")
        return redirect(url_for("settings_badges.edit_badge", badge_id=badge_id))
    badge.name = name
    badge.language = language
    file = request.files.get("file")
    if file and file.filename:
        slug = slug_for_badge(name)
        ext = os.path.splitext(file.filename)[1].lower() or ".webp"
        filename = f"{slug}{ext}"
        asset_dir = os.path.join(current_app.root_path, "assets", "badges")
        os.makedirs(asset_dir, exist_ok=True)
        file.save(os.path.join(asset_dir, filename))
        badge.filename = filename
    db.session.commit()
    flash("Badge updated", "success")
    return redirect(url_for("settings_badges.list_badges"))
