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

from ..app import db
from ..models import MaterialDefault, MaterialsOption, WorkshopType, Language
from ..shared.rbac import admin_required
from ..shared.regions import get_region_options

bp = Blueprint('settings_material_defaults', __name__, url_prefix='/settings/material-defaults')

FORMAT_CHOICES = ['Digital', 'Physical', 'Self-paced']
DELIVERY_CHOICES = ['Onsite', 'Virtual', 'Self-paced', 'Hybrid']


def _all_items():
    return MaterialsOption.query.order_by(MaterialsOption.title).all()


@bp.get('/')
@admin_required
def list_defaults(current_user):
    defaults = MaterialDefault.query.order_by(MaterialDefault.id).all()
    items = {f"materials_options:{o.id}": o for o in _all_items()}
    return render_template(
        'settings_material_defaults/list.html',
        defaults=defaults,
        items=items,
    )


@bp.get('/new')
@admin_required
def new_default(current_user):
    workshop_types = WorkshopType.query.order_by(WorkshopType.name).all()
    materials = _all_items()
    langs = (
        Language.query.filter_by(is_active=True)
        .order_by(Language.sort_order, Language.name)
        .all()
    )
    return render_template(
        'settings_material_defaults/form.html',
        default=None,
        workshop_types=workshop_types,
        materials=materials,
        regions=get_region_options(),
        delivery_choices=DELIVERY_CHOICES,
        format_choices=FORMAT_CHOICES,
        languages=langs,
    )


@bp.post('/new')
@admin_required
def create_default(current_user):
    if request.form.get('csrf_token') != flask_session.get('_csrf_token'):
        abort(400)
    wt_id = request.form.get('workshop_type_id', type=int)
    delivery_type = (request.form.get('delivery_type') or '').strip()
    region_code = request.form.get('region_code')
    language = request.form.get('language')
    catalog_ref = (request.form.get('catalog_ref') or '').strip()
    default_format = request.form.get('default_format')
    active = bool(request.form.get('active'))
    if not all([wt_id, delivery_type, region_code, language, catalog_ref, default_format]):
        flash('All fields required', 'error')
        return redirect(url_for('settings_material_defaults.new_default'))
    if not catalog_ref.startswith('materials_options:'):
        flash('Invalid material item', 'error')
        return redirect(url_for('settings_material_defaults.new_default'))
    opt_id = catalog_ref.split(':', 1)[1]
    opt = db.session.get(MaterialsOption, int(opt_id))
    if not opt:
        flash('Material item not found', 'error')
        return redirect(url_for('settings_material_defaults.new_default'))
    rule = MaterialDefault(
        workshop_type_id=wt_id,
        delivery_type=delivery_type,
        region_code=region_code,
        language=language,
        catalog_ref=f'materials_options:{opt.id}',
        default_format=default_format,
        active=active,
    )
    db.session.add(rule)
    db.session.commit()
    flash('Rule created', 'success')
    return redirect(url_for('settings_material_defaults.list_defaults'))


@bp.get('/<int:def_id>/edit')
@admin_required
def edit_default(def_id, current_user):
    rule = MaterialDefault.query.get_or_404(def_id)
    workshop_types = WorkshopType.query.order_by(WorkshopType.name).all()
    materials = _all_items()
    langs = (
        Language.query.filter_by(is_active=True)
        .order_by(Language.sort_order, Language.name)
        .all()
    )
    return render_template(
        'settings_material_defaults/form.html',
        default=rule,
        workshop_types=workshop_types,
        materials=materials,
        regions=get_region_options(),
        delivery_choices=DELIVERY_CHOICES,
        format_choices=FORMAT_CHOICES,
        languages=langs,
    )


@bp.post('/<int:def_id>/edit')
@admin_required
def update_default(def_id, current_user):
    if request.form.get('csrf_token') != flask_session.get('_csrf_token'):
        abort(400)
    rule = MaterialDefault.query.get_or_404(def_id)
    wt_id = request.form.get('workshop_type_id', type=int)
    delivery_type = (request.form.get('delivery_type') or '').strip()
    region_code = request.form.get('region_code')
    language = request.form.get('language')
    catalog_ref = (request.form.get('catalog_ref') or '').strip()
    default_format = request.form.get('default_format')
    rule.active = bool(request.form.get('active'))
    if not all([wt_id, delivery_type, region_code, language, catalog_ref, default_format]):
        flash('All fields required', 'error')
        return redirect(url_for('settings_material_defaults.edit_default', def_id=def_id))
    if not catalog_ref.startswith('materials_options:'):
        flash('Invalid material item', 'error')
        return redirect(url_for('settings_material_defaults.edit_default', def_id=def_id))
    opt_id = catalog_ref.split(':', 1)[1]
    opt = db.session.get(MaterialsOption, int(opt_id))
    if not opt:
        flash('Material item not found', 'error')
        return redirect(url_for('settings_material_defaults.edit_default', def_id=def_id))
    rule.workshop_type_id = wt_id
    rule.delivery_type = delivery_type
    rule.region_code = region_code
    rule.language = language
    rule.catalog_ref = f'materials_options:{opt.id}'
    rule.default_format = default_format
    db.session.commit()
    flash('Rule updated', 'success')
    return redirect(url_for('settings_material_defaults.list_defaults'))
