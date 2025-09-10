from flask import Blueprint, render_template

from ..shared.rbac import admin_required

bp = Blueprint('settings_badges', __name__, url_prefix='/settings/badges')


@bp.get('/')
@bp.get('')
@admin_required
def placeholder(current_user):
    return render_template('settings_badges/placeholder.html')
