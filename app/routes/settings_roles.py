from flask import Blueprint, redirect, url_for

from ..shared.rbac import manage_users_required

bp = Blueprint("settings_roles", __name__, url_prefix="/settings")


@bp.get("/roles")
@manage_users_required
def roles_matrix(current_user):
    """Legacy redirect for the removed Roles Matrix page.

    The Role Matrix now lives as a view-only modal on the Users page.
    Navigating to the old `/settings/roles` URL simply redirects to the
    Users listing where the matrix can be opened.
    """
    return redirect(url_for("users.list_users"))
