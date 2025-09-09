from __future__ import annotations

from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash, session as flask_session, abort

from ..app import db, User
from ..models import Session, SessionShipping, Client, WorkshopType

bp = Blueprint('materials_only', __name__)

@bp.route('/materials-only', methods=['GET', 'POST'])
def create():
    user_id = flask_session.get('user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    user = db.session.get(User, user_id)
    if not (user.is_app_admin or user.is_admin or getattr(user, 'is_kcrm', False)):
        abort(403)
    if request.method == 'POST':
        title = request.form.get('title')
        client_id = request.form.get('client_id', type=int)
        region = request.form.get('region')
        language = request.form.get('language')
        workshop_type_id = request.form.get('workshop_type_id', type=int)
        if not title or not client_id or not workshop_type_id:
            flash('Title, Client, and Workshop Type required', 'error')
        else:
            sess = Session(
                title=title,
                client_id=client_id,
                region=region,
                workshop_language=language,
                workshop_type_id=workshop_type_id,
                delivery_type='Material Order',
                start_date=date.today(),
                end_date=date.today(),
                materials_only=True,
            )
            db.session.add(sess)
            db.session.flush()
            shipment = SessionShipping(
                session_id=sess.id,
                order_type='Client-run Bulk order',
                status='New',
                credits=2,
                material_sets=0,
            )
            db.session.add(shipment)
            db.session.commit()
            flash('Saved', 'info')
            return redirect(url_for('materials.materials_view', session_id=sess.id))
    clients = Client.query.order_by(Client.name).all()
    workshop_types = WorkshopType.query.order_by(WorkshopType.name).all()
    return render_template('materials_only.html', clients=clients, workshop_types=workshop_types)
