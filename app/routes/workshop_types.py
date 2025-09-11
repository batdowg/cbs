from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    session as flask_session,
)
import re

from ..app import db, User
from ..models import (
    WorkshopType,
    AuditLog,
    PreworkTemplate,
    PreworkQuestion,
    CertificateTemplateSeries,
    MaterialsOption,
    WorkshopTypeMaterialDefault,
    Language,
)
from ..shared.html import sanitize_html
from ..shared.languages import get_language_options, code_to_label
from ..shared.regions import get_region_options
from flask import jsonify

bp = Blueprint("workshop_types", __name__, url_prefix="/workshop-types")

FORMAT_CHOICES = ["Digital", "Physical", "Self-paced"]
DELIVERY_CHOICES = ["Onsite", "Virtual", "Self-paced", "Hybrid"]


def lang_key(lang) -> str:
    """Return a lowercase language identifier for an object or string."""
    if isinstance(lang, str):
        return lang.lower()
    return (
        getattr(lang, "code", None)
        or getattr(lang, "abbr", None)
        or getattr(lang, "short_code", None)
        or getattr(lang, "name", None)
        or ""
    ).lower()


def query_material_options(delivery_type: str, lang_name: str, include_bulk: bool = False):
    """Return material options matching delivery type and language.

    Language filtering uses ``Language.name`` because the table stores names
    only. When ``include_bulk`` is false, options with "bulk" in the title or
    description and the explicit "Client-run Bulk order" catalog are excluded.
    ``delivery_type`` is reserved for future family rules.
    """

    q = MaterialsOption.query.filter(MaterialsOption.is_active == True)
    if lang_name:
        q = q.join(MaterialsOption.languages).filter(
            Language.name.ilike(lang_name)
        )
    if not include_bulk:
        bulk = "%bulk%"
        q = q.filter(
            MaterialsOption.order_type != "Client-run Bulk order",
            db.func.lower(MaterialsOption.title).notlike(bulk),
            db.or_(
                MaterialsOption.description.is_(None),
                db.func.lower(MaterialsOption.description).notlike(bulk),
            ),
        )
    return q.order_by(MaterialsOption.order_type, MaterialsOption.title).all()


def staff_required(fn):
    from functools import wraps
    from flask import session as flask_session

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login"))
        user = db.session.get(User, user_id)
        if not user or not (user.is_app_admin or user.is_admin):
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


@bp.get("/material-options")
@staff_required
def material_options(current_user):
    delivery = request.args.get("delivery_type") or ""
    lang_code = request.args.get("lang") or ""
    lang_name = code_to_label(lang_code)
    include_bulk = bool(request.args.get("include_bulk"))
    items = query_material_options(delivery, lang_name, include_bulk)
    results = []
    for item in items:
        langs = sorted(l.name.lower() for l in item.languages)
        label = f"{item.order_type} • {item.title}"
        if langs:
            label += f" • [{', '.join(langs)}]"
        results.append({"id": item.id, "label": label})
    return jsonify(items=results)


@bp.get("/")
@staff_required
def list_types(current_user):
    types = WorkshopType.query.order_by(WorkshopType.code).all()
    return render_template("workshop_types/list.html", types=types)


@bp.get("/new")
@staff_required
def new_type(current_user):
    series = (
        CertificateTemplateSeries.query.filter_by(is_active=True)
        .order_by(CertificateTemplateSeries.code)
        .all()
    )
    materials_options = (
        MaterialsOption.query.filter_by(is_active=True)
        .order_by(MaterialsOption.title)
        .all()
    )
    return render_template(
        "workshop_types/form.html",
        wt=None,
        language_options=get_language_options(),
        series=series,
        materials_options=materials_options,
    )


@bp.post("/new")
@staff_required
def create_type(current_user):
    if request.form.get("csrf_token") != flask_session.get("_csrf_token"):
        abort(400)
    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()
    if not code or not name:
        flash("Code and Name required", "error")
        return redirect(url_for("workshop_types.new_type"))
    if WorkshopType.query.filter(db.func.upper(WorkshopType.code) == code).first():
        flash("Code already exists", "error")
        return redirect(url_for("workshop_types.new_type"))
    series_code = (request.form.get("cert_series") or "").strip()
    if not series_code:
        flash("Certificate series required", "error")
        return redirect(url_for("workshop_types.new_type"))
    if not CertificateTemplateSeries.query.filter_by(
        code=series_code, is_active=True
    ).first():
        flash("Invalid certificate series", "error")
        return redirect(url_for("workshop_types.new_type"))
    langs = request.form.getlist("supported_languages")
    wt = WorkshopType(
        code=code,
        name=name,
        status=request.form.get("status") or "active",
        description=request.form.get("description") or None,
        simulation_based=bool(request.form.get("simulation_based")),
        supported_languages=langs or ["en"],
        cert_series=series_code,
    )
    dmo = request.form.get("default_materials_option_id")
    wt.default_materials_option_id = int(dmo) if dmo else None
    db.session.add(wt)
    db.session.flush()
    db.session.add(
        AuditLog(
            user_id=current_user.id,
            action="workshop_type_create",
            details=f"id={wt.id} code={wt.code}",
        )
    )
    db.session.commit()
    flash("Workshop Type created", "success")
    return redirect(url_for("workshop_types.list_types"))


@bp.get("/<int:type_id>/edit")
@staff_required
def edit_type(type_id: int, current_user):
    wt = db.session.get(WorkshopType, type_id)
    if not wt:
        abort(404)
    series = (
        CertificateTemplateSeries.query.filter_by(is_active=True)
        .order_by(CertificateTemplateSeries.code)
        .all()
    )
    materials_options = (
        MaterialsOption.query.filter_by(is_active=True)
        .order_by(MaterialsOption.title)
        .all()
    )
    language_options = get_language_options()
    defaults = (
        WorkshopTypeMaterialDefault.query.filter_by(workshop_type_id=wt.id)
        .order_by(WorkshopTypeMaterialDefault.id)
        .all()
    )
    selected_opts: dict[int, dict[str, str]] = {}
    for d in defaults:
        opt_id = 0
        if d.catalog_ref.startswith("materials_options:"):
            try:
                opt_id = int(d.catalog_ref.split(":", 1)[1])
            except ValueError:
                opt_id = 0
        if opt_id:
            opt = db.session.get(MaterialsOption, opt_id)
            if opt:
                langs = sorted(l.name.lower() for l in opt.languages)
                label = f"{opt.order_type} • {opt.title}"
                if langs:
                    label += f" • [{', '.join(langs)}]"
                selected_opts[d.id] = {"id": opt.id, "label": label}
    supported_langs = sorted(
        {lang_key(lang) for lang in (wt.supported_languages or []) if lang_key(lang)}
    )
    return render_template(
        "workshop_types/form.html",
        wt=wt,
        current_user=current_user,
        language_options=language_options,
        supported_langs=supported_langs,
        series=series,
        materials_options=materials_options,
        defaults=defaults,
        selected_opts=selected_opts,
        regions=get_region_options(),
        delivery_choices=DELIVERY_CHOICES,
        format_choices=FORMAT_CHOICES,
    )


@bp.post("/<int:type_id>/edit")
@staff_required
def update_type(type_id: int, current_user):
    wt = db.session.get(WorkshopType, type_id)
    if not wt:
        abort(404)
    if request.form.get("csrf_token") != flask_session.get("_csrf_token"):
        abort(400)
    wt.name = request.form.get("name") or wt.name
    wt.status = request.form.get("status") or wt.status
    wt.description = request.form.get("description") or None
    wt.simulation_based = bool(request.form.get("simulation_based"))
    langs = request.form.getlist("supported_languages")
    wt.supported_languages = langs or ["en"]
    dmo = request.form.get("default_materials_option_id")
    wt.default_materials_option_id = int(dmo) if dmo else None
    series_code = (request.form.get("cert_series") or "").strip()
    if not series_code:
        flash("Certificate series required", "error")
        return redirect(url_for("workshop_types.edit_type", type_id=wt.id))
    if not CertificateTemplateSeries.query.filter_by(
        code=series_code, is_active=True
    ).first():
        flash("Invalid certificate series", "error")
        return redirect(url_for("workshop_types.edit_type", type_id=wt.id))
    wt.cert_series = series_code
    defaults = (
        WorkshopTypeMaterialDefault.query.filter_by(workshop_type_id=wt.id)
        .order_by(WorkshopTypeMaterialDefault.id)
        .all()
    )
    pattern = re.compile(r"defaults\[(.+?)\]\[(.+?)\]")
    form_defaults: dict[str, dict[str, str]] = {}
    for key, value in request.form.items():
        m = pattern.fullmatch(key)
        if m:
            row, field = m.groups()
            form_defaults.setdefault(row, {})[field] = value
    for d in list(defaults):
        data = form_defaults.get(str(d.id), {})
        if data.get("remove"):
            db.session.delete(d)
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    action="wt_material_default_delete",
                    details=f"id={d.id} wt={wt.id}",
                )
            )
            continue
        delivery_type = data.get("delivery_type") or ""
        region_code = data.get("region_code") or ""
        language = data.get("language") or ""
        opt_val = data.get("material_option_id") or ""
        default_format = data.get("default_format") or ""
        active = bool(data.get("active"))
        if not all([delivery_type, region_code, language, opt_val, default_format]):
            flash("All fields required", "error")
            return redirect(
                url_for("workshop_types.edit_type", type_id=wt.id) + "#defaults"
            )
        try:
            opt_id = int(opt_val)
        except ValueError:
            flash(f"Invalid material item (row {d.id})", "error")
            return redirect(
                url_for("workshop_types.edit_type", type_id=wt.id) + "#defaults"
            )
        opt = db.session.get(MaterialsOption, opt_id)
        if not opt:
            flash(f"Invalid material item (row {d.id})", "error")
            return redirect(
                url_for("workshop_types.edit_type", type_id=wt.id) + "#defaults"
            )
        d.delivery_type = delivery_type
        d.region_code = region_code
        d.language = language
        d.catalog_ref = f"materials_options:{opt_id}"
        d.default_format = default_format
        d.active = active
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                action="wt_material_default_update",
                details=f"id={d.id} wt={wt.id}",
            )
        )
    new_data = form_defaults.get("new", {})
    delivery_type = new_data.get("delivery_type") or ""
    region_code = new_data.get("region_code") or ""
    language = new_data.get("language") or ""
    opt_val = new_data.get("material_option_id") or ""
    default_format = new_data.get("default_format") or ""
    active = bool(new_data.get("active"))
    if any([delivery_type, region_code, language, opt_val, default_format]):
        if not all([delivery_type, region_code, language, opt_val, default_format]):
            flash("All fields required", "error")
            return redirect(
                url_for("workshop_types.edit_type", type_id=wt.id) + "#defaults"
            )
        try:
            opt_id = int(opt_val)
        except ValueError:
            flash("Invalid material item (row new)", "error")
            return redirect(
                url_for("workshop_types.edit_type", type_id=wt.id) + "#defaults"
            )
        opt = db.session.get(MaterialsOption, opt_id)
        if not opt:
            flash("Invalid material item (row new)", "error")
            return redirect(
                url_for("workshop_types.edit_type", type_id=wt.id) + "#defaults"
            )
        rule = WorkshopTypeMaterialDefault(
            workshop_type_id=wt.id,
            delivery_type=delivery_type,
            region_code=region_code,
            language=language,
            catalog_ref=f"materials_options:{opt_id}",
            default_format=default_format,
            active=active,
        )
        db.session.add(rule)
        db.session.flush()
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                action="wt_material_default_create",
                details=f"id={rule.id} wt={wt.id}",
            )
        )
    db.session.add(
        AuditLog(
            user_id=current_user.id,
            action="workshop_type_update",
            details=f"id={wt.id}",
        )
    )
    db.session.commit()
    flash("Workshop Type updated", "success")
    return redirect(url_for("workshop_types.list_types"))


@bp.route("/<int:type_id>/defaults", methods=["GET", "POST"])
@staff_required
def default_materials(type_id: int, current_user):
    return redirect(
        url_for("workshop_types.edit_type", type_id=type_id) + "#defaults",
        code=302,
    )


@bp.route("/<int:type_id>/prework", methods=["GET", "POST"])
@staff_required
def prework(type_id: int, current_user):
    wt = db.session.get(WorkshopType, type_id)
    if not wt:
        abort(404)
    tpl = PreworkTemplate.query.filter_by(workshop_type_id=wt.id).first()
    if request.method == "POST":
        if not tpl:
            tpl = PreworkTemplate(workshop_type_id=wt.id)
        tpl.is_active = bool(request.form.get("is_active"))
        tpl.require_completion = bool(request.form.get("require_completion"))
        tpl.info_html = sanitize_html(request.form.get("info") or "")
        questions = []
        for i in range(1, 11):
            text = sanitize_html(request.form.get(f"text_{i}") or "")
            if not text:
                continue
            kind = request.form.get(f"kind_{i}") or "TEXT"
            min_items = None
            max_items = None
            if kind == "LIST":
                try:
                    min_items = int(request.form.get(f"min_{i}") or 3)
                except ValueError:
                    min_items = 3
                try:
                    max_items = int(request.form.get(f"max_{i}") or 5)
                except ValueError:
                    max_items = 5
                if min_items < 1:
                    min_items = 1
                if max_items < min_items:
                    max_items = min_items
                if max_items > 10:
                    max_items = 10
            questions.append((text, kind, min_items, max_items))
        if tpl.id:
            PreworkQuestion.query.filter_by(template_id=tpl.id).delete()
        for idx, (text, kind, min_items, max_items) in enumerate(questions, start=1):
            db.session.add(
                PreworkQuestion(
                    template=tpl,
                    position=idx,
                    text=text,
                    required=True,
                    kind=kind,
                    min_items=min_items,
                    max_items=max_items,
                )
            )
        db.session.add(tpl)
        db.session.commit()
        flash("Prework template saved", "success")
        return redirect(url_for("workshop_types.prework", type_id=wt.id))
    questions = []
    if tpl:
        for q in sorted(tpl.questions, key=lambda q: q.position):
            questions.append(
                {
                    "text": q.text,
                    "kind": q.kind,
                    "min_items": q.min_items,
                    "max_items": q.max_items,
                }
            )
    return render_template(
        "workshop_types/prework.html",
        wt=wt,
        template=tpl,
        questions=questions,
    )
