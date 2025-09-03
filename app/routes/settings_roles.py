from flask import Blueprint, render_template

from ..constants import PERMISSIONS_MATRIX, ROLES_MATRIX_VERSION
from ..utils.rbac import admin_required

bp = Blueprint("settings_roles", __name__, url_prefix="/settings")

@bp.get("/roles")
@admin_required
def roles_matrix(current_user):
    return render_template("settings_roles.html", matrix=PERMISSIONS_MATRIX, version=ROLES_MATRIX_VERSION)
