from flask import Blueprint, render_template

from .sessions import staff_required

bp = Blueprint("certificates", __name__, url_prefix="/certificates")


@bp.get("")
@staff_required
def index(current_user):
    return render_template("certificates.html")
