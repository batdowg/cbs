from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..app import db, User
from ..models import WorkshopType, AuditLog, PreworkTemplate, PreworkQuestion
from ..constants import BADGE_CHOICES
from ..utils.html import sanitize_html
from ..utils.languages import get_language_options

bp = Blueprint('workshop_types', __name__, url_prefix='/workshop-types')


def staff_required(fn):
    from functools import wraps
    from flask import session as flask_session

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get('user_id')
        if not user_id:
            return redirect(url_for('auth.login'))
        user = db.session.get(User, user_id)
        if not user or not (user.is_app_admin or user.is_admin):
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


@bp.get('/')
@staff_required
def list_types(current_user):
    types = WorkshopType.query.order_by(WorkshopType.code).all()
    return render_template('workshop_types/list.html', types=types)


@bp.get('/new')
@staff_required
def new_type(current_user):
    return render_template('workshop_types/form.html', wt=None, badge_choices=BADGE_CHOICES, language_options=get_language_options())


@bp.post('/new')
@staff_required
def create_type(current_user):
    code = (request.form.get('code') or '').strip().upper()
    name = (request.form.get('name') or '').strip()
    if not code or not name:
        flash('Code and Name required', 'error')
        return redirect(url_for('workshop_types.new_type'))
    if WorkshopType.query.filter(db.func.upper(WorkshopType.code) == code).first():
        flash('Code already exists', 'error')
        return redirect(url_for('workshop_types.new_type'))
    langs = request.form.getlist('supported_languages')
    wt = WorkshopType(
        code=code,
        name=name,
        status=request.form.get('status') or 'active',
        description=request.form.get('description') or None,
        badge=request.form.get('badge') or None,
        simulation_based=bool(request.form.get('simulation_based')),
        supported_languages=langs or ['en'],
        cert_series=(request.form.get('cert_series') or 'fn').strip() or 'fn',
    )
    db.session.add(wt)
    db.session.flush()
    db.session.add(
        AuditLog(
            user_id=current_user.id,
            action='workshop_type_create',
            details=f'id={wt.id} code={wt.code}',
        )
    )
    db.session.commit()
    flash('Workshop Type created', 'success')
    return redirect(url_for('workshop_types.list_types'))


@bp.get('/<int:type_id>/edit')
@staff_required
def edit_type(type_id: int, current_user):
    wt = db.session.get(WorkshopType, type_id)
    if not wt:
        abort(404)
    return render_template('workshop_types/form.html', wt=wt, badge_choices=BADGE_CHOICES, language_options=get_language_options())


@bp.post('/<int:type_id>/edit')
@staff_required
def update_type(type_id: int, current_user):
    wt = db.session.get(WorkshopType, type_id)
    if not wt:
        abort(404)
    wt.name = request.form.get('name') or wt.name
    wt.status = request.form.get('status') or wt.status
    wt.description = request.form.get('description') or None
    wt.badge = request.form.get('badge') or None
    wt.simulation_based = bool(request.form.get('simulation_based'))
    langs = request.form.getlist('supported_languages')
    wt.supported_languages = langs or ['en']
    wt.cert_series = (request.form.get('cert_series') or 'fn').strip() or 'fn'
    db.session.add(
        AuditLog(
            user_id=current_user.id,
            action='workshop_type_update',
            details=f'id={wt.id}',
        )
    )
    db.session.commit()
    flash('Workshop Type updated', 'success')
    return redirect(url_for('workshop_types.list_types'))


@bp.route('/<int:type_id>/prework', methods=['GET', 'POST'])
@staff_required
def prework(type_id: int, current_user):
    wt = db.session.get(WorkshopType, type_id)
    if not wt:
        abort(404)
    tpl = PreworkTemplate.query.filter_by(workshop_type_id=wt.id).first()
    if request.method == 'POST':
        if not tpl:
            tpl = PreworkTemplate(workshop_type_id=wt.id)
        tpl.is_active = bool(request.form.get('is_active'))
        tpl.require_completion = bool(request.form.get('require_completion'))
        tpl.info_html = sanitize_html(request.form.get('info') or '')
        questions = []
        for i in range(1, 11):
            text = sanitize_html(request.form.get(f'text_{i}') or '')
            if not text:
                continue
            kind = request.form.get(f'kind_{i}') or 'TEXT'
            min_items = None
            max_items = None
            if kind == 'LIST':
                try:
                    min_items = int(request.form.get(f'min_{i}') or 3)
                except ValueError:
                    min_items = 3
                try:
                    max_items = int(request.form.get(f'max_{i}') or 5)
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
        flash('Prework template saved', 'success')
        return redirect(url_for('workshop_types.prework', type_id=wt.id))
    questions = []
    if tpl:
        for q in sorted(tpl.questions, key=lambda q: q.position):
            questions.append(
                {
                    'text': q.text,
                    'kind': q.kind,
                    'min_items': q.min_items,
                    'max_items': q.max_items,
                }
            )
    return render_template(
        'workshop_types/prework.html',
        wt=wt,
        template=tpl,
        questions=questions,
    )
