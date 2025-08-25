from pathlib import Path
from flask import Blueprint, abort, send_file

bp = Blueprint("assets", __name__)

_allowed = {
    "foundations": "foundation.webp",
    "practitioner": "practitioner.webp",
    "advanced": "advanced.webp",
    "expert": "expert.webp",
    "coach": "coach.webp",
    "facilitator": "facilitator.webp",
    "program-leader": "program-leader.webp",
}

_repo_dir = Path(__file__).resolve().parents[1] / "assets" / "badges"
_fallback_dir = Path("/app/assets")

@bp.get("/badges/<slug>.webp")
def badge(slug: str):
    fname = _allowed.get(slug.lower())
    if not fname:
        abort(404)
    for d in (_repo_dir, _fallback_dir):
        p = d / fname
        if p.exists():
            return send_file(p, as_attachment=True, download_name=fname, mimetype="image/webp")
    abort(404)
