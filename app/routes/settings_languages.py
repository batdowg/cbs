from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..app import db
from ..models import Language
from ..utils.rbac import admin_required

bp = Blueprint('settings_languages', __name__, url_prefix='/settings/languages')


@bp.get('/')
@admin_required
def list_langs(current_user):
    langs = Language.query.order_by(Language.sort_order, Language.name).all()
    return render_template('settings_languages/list.html', langs=langs)


@bp.get('/new')
@admin_required
def new_lang(current_user):
    return render_template('settings_languages/form.html', lang=None)


@bp.post('/new')
@admin_required
def create_lang(current_user):
    name = (request.form.get('name') or '').strip()
    sort_order = request.form.get('sort_order') or '100'
    if not name:
        flash('Name required', 'error')
        return redirect(url_for('settings_languages.new_lang'))
    existing = Language.query.filter(db.func.lower(Language.name) == name.lower()).first()
    if existing:
        flash('Name must be unique', 'error')
        return redirect(url_for('settings_languages.new_lang'))
    lang = Language(name=name, sort_order=int(sort_order))
    db.session.add(lang)
    db.session.commit()
    flash('Language created', 'success')
    return redirect(url_for('settings_languages.list_langs'))


@bp.get('/<int:lang_id>/edit')
@admin_required
def edit_lang(lang_id: int, current_user):
    lang = db.session.get(Language, lang_id)
    if not lang:
        abort(404)
    return render_template('settings_languages/form.html', lang=lang)


@bp.post('/<int:lang_id>/edit')
@admin_required
def update_lang(lang_id: int, current_user):
    lang = db.session.get(Language, lang_id)
    if not lang:
        abort(404)
    name = (request.form.get('name') or '').strip()
    sort_order = request.form.get('sort_order') or '100'
    if not name:
        flash('Name required', 'error')
        return redirect(url_for('settings_languages.edit_lang', lang_id=lang_id))
    existing = Language.query.filter(
        db.func.lower(Language.name) == name.lower(), Language.id != lang.id
    ).first()
    if existing:
        flash('Name must be unique', 'error')
        return redirect(url_for('settings_languages.edit_lang', lang_id=lang_id))
    lang.name = name
    lang.sort_order = int(sort_order)
    lang.is_active = bool(request.form.get('is_active'))
    db.session.commit()
    flash('Language updated', 'success')
    return redirect(url_for('settings_languages.list_langs'))


@bp.post('/<int:lang_id>/toggle')
@admin_required
def toggle_lang(lang_id: int, current_user):
    lang = db.session.get(Language, lang_id)
    if not lang:
        abort(404)
    lang.is_active = not lang.is_active
    db.session.commit()
    flash('Language activated' if lang.is_active else 'Language deactivated', 'info')
    return redirect(url_for('settings_languages.list_langs'))
