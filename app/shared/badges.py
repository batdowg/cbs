from __future__ import annotations

import os
import shutil


from flask import current_app, url_for
from sqlalchemy import func

from ..models import BadgeImage


def slug_for_badge(name: str) -> str:
    return (name or "").replace(" ", "").lower()


def best_badge_url(name: str | None) -> str | None:
    if not name:
        return None

    site_root = current_app.config.get("SITE_ROOT", "/srv")
    site_dir = os.path.join(site_root, "badges")
    asset_dir = os.path.join(current_app.root_path, "assets", "badges")
    os.makedirs(site_dir, exist_ok=True)

    filename = None
    badge = BadgeImage.query.filter(func.lower(BadgeImage.name) == name.lower()).first()
    if badge:
        filename = badge.filename

    candidates: list[str]
    if filename:
        candidates = [filename]
    else:
        slug = slug_for_badge(name)
        if not slug:
            return None
        candidates = [f"{slug}.webp", f"{slug}.png"]

    for fn in candidates:
        site_path = os.path.join(site_dir, fn)
        asset_path = os.path.join(asset_dir, fn)
        slug = os.path.splitext(fn)[0]
        ext = os.path.splitext(fn)[1][1:]
        if os.path.isfile(site_path):
            return url_for("badge_file", slug=slug, ext=ext)
        if os.path.isfile(asset_path):
            try:
                shutil.copyfile(asset_path, site_path)
            except OSError:
                pass
            return url_for("badge_file", slug=slug, ext=ext)

    return None
