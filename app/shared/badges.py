from __future__ import annotations

import os
import shutil

from flask import current_app, url_for


def slug_for_badge(name: str) -> str:
    return (name or "").replace(" ", "").lower()


def best_badge_url(name: str | None) -> str | None:
    if not name:
        return None
    slug = slug_for_badge(name)
    if not slug:
        return None

    site_root = current_app.config.get("SITE_ROOT", "/srv")
    site_dir = os.path.join(site_root, "badges")
    asset_dir = os.path.join(current_app.root_path, "assets", "badges")
    os.makedirs(site_dir, exist_ok=True)
    for ext in ("webp", "png"):
        filename = f"{slug}.{ext}"
        site_path = os.path.join(site_dir, filename)
        asset_path = os.path.join(asset_dir, filename)
        if os.path.isfile(site_path):
            return url_for("badge_file", slug=slug, ext=ext)
        if os.path.isfile(asset_path):
            try:
                shutil.copyfile(asset_path, site_path)
            except OSError:
                pass
            return url_for("badge_file", slug=slug, ext=ext)
    return None
