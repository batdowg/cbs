from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from ..app import db, User
from ..utils.acl import can_manage_users
from ..utils.nav import build_menu, VIEW_FILTERS

bp = Blueprint("settings_sitemap", __name__, url_prefix="/settings/sitemap")


def _current_user() -> User | Response:
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))
    user = db.session.get(User, user_id)
    if not user or not can_manage_users(user):
        abort(403)
    return user


VIEW_ROLES = {
    "ADMIN": ["Sys Admin", "Admin"],
    "SESSION_MANAGER": ["CRM"],
    "MATERIALS": ["Admin", "CRM", "Delivery", "Contractor"],
    "DELIVERY": ["Delivery", "Contractor"],
    "LEARNER": ["Participant"],
    "CSA": ["CSA"],
}


def _flatten(menu: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in menu:
        out.append(item)
        for child in item.get("children", []):
            out.extend(_flatten([child]))
    return out


def _menu_mapping() -> Dict[str, Dict[str, Any]]:
    dummy = type("Dummy", (), {
        "has_role": lambda self, role: True,
        "is_app_admin": True,
        "is_admin": True,
        "is_kcrm": True,
        "is_kt_delivery": True,
        "is_kt_contractor": True,
    })()
    mapping: Dict[str, Dict[str, Any]] = {}
    for view in VIEW_FILTERS.keys():
        menu = build_menu(dummy, view, show_resources=True)
        for item in _flatten(menu):
            ep = item.get("endpoint")
            if not ep:
                continue
            entry = mapping.setdefault(ep, {"label": item["label"], "roles": set()})
            entry["roles"].update(VIEW_ROLES.get(view, []))
    return mapping


def _gather_routes() -> List[Dict[str, Any]]:
    menu_map = _menu_mapping()
    routes: List[Dict[str, Any]] = []
    for rule in current_app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
        view_func = current_app.view_functions[rule.endpoint]
        template = ""
        for const in getattr(view_func, "__code__").co_consts:
            if isinstance(const, str) and const.endswith(".html"):
                template = const
        roles = []
        menu_label = None
        if rule.endpoint in menu_map:
            menu_label = menu_map[rule.endpoint]["label"]
            roles = sorted(menu_map[rule.endpoint]["roles"])
        area = "Public"
        if any(r in {"Sys Admin", "Admin"} for r in roles):
            area = "Admin"
        elif any(r in {"CRM", "Delivery", "Contractor"} for r in roles):
            area = "Staff"
        elif roles:
            area = "Participant"
        link = rule.rule if "GET" in methods else ""
        notes = "protected" if "GET" not in methods else ""
        routes.append(
            {
                "path": rule.rule,
                "methods": ",".join(methods),
                "endpoint": rule.endpoint,
                "menu_label": menu_label,
                "roles": ",".join(roles),
                "template": template,
                "notes": notes,
                "link": link,
                "area": area,
            }
        )
    return routes


@bp.get("/")
def sitemap() -> Response:
    user = _current_user()
    role = request.args.get("role")
    area = request.args.get("area")
    q = request.args.get("q", "").lower()
    routes = _gather_routes()
    filtered = [r for r in routes if (not role or role in r["roles"]) and (not area or r["area"] == area) and (q in r["path"].lower() or q in r["endpoint"].lower() or q in (r["menu_label"] or "").lower())]
    if request.args.get("export") == "csv":
        sio = StringIO()
        writer = csv.DictWriter(sio, fieldnames=["path", "methods", "endpoint", "menu_label", "roles", "template", "notes", "link"])
        writer.writeheader()
        for r in filtered:
            writer.writerow({k: r[k] for k in writer.fieldnames})
        return Response(
            sio.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=sitemap.csv"},
        )
    return render_template("settings_sitemap.html", routes=filtered, role=role, area=area, q=request.args.get("q", ""))


@bp.post("/write")
def write_snapshot() -> Response:
    _current_user()
    routes = _gather_routes()
    root = Path(current_app.root_path).parent
    lines = ["# Site Map\n", "\n", "| Path | Methods | Endpoint | Menu | Roles | Template | Notes |", "\n", "|---|---|---|---|---|---|---|\n"]
    for r in routes:
        lines.append(
            f"| {r['path']} | {r['methods']} | {r['endpoint']} | {r['menu_label'] or ''} | {r['roles']} | {r['template']} | {r['notes']} |\n"
        )
    (root / "SITE_MAP.md").write_text("".join(lines), encoding="utf-8")
    flash("SITE_MAP.md updated", "success")
    return redirect(url_for("settings_sitemap.sitemap"))


@bp.get("/snapshot")
def snapshot_file() -> Response:
    root = Path(current_app.root_path).parent
    return send_from_directory(root, "SITE_MAP.md", as_attachment=False)
