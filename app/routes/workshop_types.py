from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..app import db, User
from ..models import WorkshopType, AuditLog

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
    return render_template('workshop_types/form.html', wt=None)


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
    wt = WorkshopType(
        code=code,
        name=name,
        status=request.form.get('status') or 'active',
        description=request.form.get('description') or None,
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
    return render_template('workshop_types/form.html', wt=wt)


@bp.post('/<int:type_id>/edit')
@staff_required
def update_type(type_id: int, current_user):
    wt = db.session.get(WorkshopType, type_id)
    if not wt:
        abort(404)
    wt.name = request.form.get('name') or wt.name
    wt.status = request.form.get('status') or wt.status
    wt.description = request.form.get('description') or None
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
