from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..app import db
from ..models import MaterialsOption, Language
from ..shared.rbac import admin_required

bp = Blueprint('settings_materials', __name__, url_prefix='/settings/materials')

MATERIAL_MAP = {
    'standard': ('Standard workshop', 'KT-Run Standard materials'),
    'modular': ('Modular', 'KT-Run Modular materials'),
    'ldi': ('LDI', 'KT-Run LDI materials'),
    'bulk': ('Bulk order', 'Client-run Bulk order'),
    'simulation': ('Simulation', 'Simulation'),
}

FORMAT_CHOICES = ['Digital', 'Physical', 'Self-paced', 'Mixed']
QTY_BASIS_CHOICES = ['Per learner', 'Per order']


def _get_type(slug: str):
    info = MATERIAL_MAP.get(slug)
    if not info:
        abort(404)
    return info


@bp.get('/<slug>')
@admin_required
def list_options(slug: str, current_user):
    label, order_type = _get_type(slug)
    options = (
        MaterialsOption.query.filter_by(order_type=order_type)
        .order_by(MaterialsOption.title)
        .all()
    )
    return render_template(
        'settings_materials/list.html',
        options=options,
        label=label,
        slug=slug,
    )


@bp.get('/<slug>/new')
@admin_required
def new_option(slug: str, current_user):
    label, order_type = _get_type(slug)
    langs = (
        Language.query.filter_by(is_active=True)
        .order_by(Language.sort_order, Language.name)
        .all()
    )
    return render_template(
        'settings_materials/form.html',
        opt=None,
        label=label,
        slug=slug,
        format_choices=FORMAT_CHOICES,
        languages=langs,
    )


@bp.post('/<slug>/new')
@admin_required
def create_option(slug: str, current_user):
    label, order_type = _get_type(slug)
    title = (request.form.get('title') or '').strip()
    if not title:
        flash('Title required', 'error')
        return redirect(url_for('settings_materials.new_option', slug=slug))
    existing = (
        MaterialsOption.query.filter(
            MaterialsOption.order_type == order_type,
            db.func.lower(MaterialsOption.title) == title.lower(),
        ).first()
    )
    if existing:
        flash('Title must be unique', 'error')
        return redirect(url_for('settings_materials.new_option', slug=slug))
    lang_ids = [int(l) for l in request.form.getlist('language_ids') if l.isdigit()]
    langs = Language.query.filter(Language.id.in_(lang_ids)).all() if lang_ids else []
    formats = [f for f in request.form.getlist('formats') if f in FORMAT_CHOICES]
    quantity_basis = request.form.get('quantity_basis') or 'Per learner'
    if quantity_basis not in QTY_BASIS_CHOICES:
        flash('Invalid quantity basis', 'error')
        return redirect(url_for('settings_materials.new_option', slug=slug))
    opt = MaterialsOption(
        order_type=order_type,
        title=title,
        formats=formats,
        quantity_basis=quantity_basis,
    )
    opt.languages = langs
    db.session.add(opt)
    db.session.commit()
    flash('Option created', 'success')
    return redirect(url_for('settings_materials.list_options', slug=slug))


@bp.get('/<slug>/<int:opt_id>/edit')
@admin_required
def edit_option(slug: str, opt_id: int, current_user):
    label, order_type = _get_type(slug)
    opt = MaterialsOption.query.filter_by(id=opt_id, order_type=order_type).first()
    if not opt:
        abort(404)
    langs = (
        Language.query.filter_by(is_active=True)
        .order_by(Language.sort_order, Language.name)
        .all()
    )
    return render_template(
        'settings_materials/form.html',
        opt=opt,
        label=label,
        slug=slug,
        format_choices=FORMAT_CHOICES,
        languages=langs,
    )


@bp.post('/<slug>/<int:opt_id>/edit')
@admin_required
def update_option(slug: str, opt_id: int, current_user):
    label, order_type = _get_type(slug)
    opt = MaterialsOption.query.filter_by(id=opt_id, order_type=order_type).first()
    if not opt:
        abort(404)
    title = (request.form.get('title') or '').strip()
    if not title:
        flash('Title required', 'error')
        return redirect(url_for('settings_materials.edit_option', slug=slug, opt_id=opt_id))
    existing = (
        MaterialsOption.query.filter(
            MaterialsOption.order_type == order_type,
            db.func.lower(MaterialsOption.title) == title.lower(),
            MaterialsOption.id != opt.id,
        ).first()
    )
    if existing:
        flash('Title must be unique', 'error')
        return redirect(url_for('settings_materials.edit_option', slug=slug, opt_id=opt_id))
    opt.title = title
    lang_ids = [int(l) for l in request.form.getlist('language_ids') if l.isdigit()]
    opt.languages = Language.query.filter(Language.id.in_(lang_ids)).all() if lang_ids else []
    opt.formats = [f for f in request.form.getlist('formats') if f in FORMAT_CHOICES]
    quantity_basis = request.form.get('quantity_basis') or 'Per learner'
    if quantity_basis not in QTY_BASIS_CHOICES:
        flash('Invalid quantity basis', 'error')
        return redirect(url_for('settings_materials.edit_option', slug=slug, opt_id=opt_id))
    opt.quantity_basis = quantity_basis
    opt.is_active = bool(request.form.get('is_active'))
    db.session.commit()
    flash('Option updated', 'success')
    return redirect(url_for('settings_materials.list_options', slug=slug))


@bp.post('/<slug>/<int:opt_id>/toggle')
@admin_required
def toggle_option(slug: str, opt_id: int, current_user):
    label, order_type = _get_type(slug)
    opt = MaterialsOption.query.filter_by(id=opt_id, order_type=order_type).first()
    if not opt:
        abort(404)
    opt.is_active = not opt.is_active
    db.session.commit()
    flash('Option activated' if opt.is_active else 'Option deactivated', 'info')
    return redirect(url_for('settings_materials.list_options', slug=slug))
