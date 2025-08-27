from __future__ import annotations

import os
from flask import current_app


def slug_for_badge(name: str) -> str:
    return (name or "").replace(" ", "").lower()


def best_badge_url(name: str | None) -> str | None:
    if not name:
        return None
    slug = slug_for_badge(name)
    if not slug:
        return None

    site_dir = "/srv/badges"
    asset_dir = os.path.join(current_app.root_path, "assets", "badges")
    for ext in ("webp", "png"):
        filename = f"{slug}.{ext}"
        if os.path.isfile(os.path.join(site_dir, filename)) or os.path.isfile(
            os.path.join(asset_dir, filename)
        ):
            return f"/badges/{slug}.{ext}"
    return None
