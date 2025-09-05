from __future__ import annotations

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from ..app import db, User
from ..models import SimulationOutline, AuditLog
from ..utils.acl import is_staff_user

bp = Blueprint("settings_simulations", __name__, url_prefix="/settings/simulations")


def _current_user(require_edit: bool = False) -> User | Response:
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))
    user = db.session.get(User, user_id)
    if not user:
        abort(403)
    can_view = is_staff_user(user) or user.is_kt_delivery or user.is_kt_contractor
    if not can_view:
        abort(403)
    if require_edit and not (is_staff_user(user) or user.is_kt_delivery):
        abort(403)
    return user


@bp.get("/")
def list_simulations():
    current_user = _current_user()
    if isinstance(current_user, Response):
        return current_user
    sims = SimulationOutline.query.order_by(SimulationOutline.number).all()
    return render_template(
        "settings_simulations/list.html",
        simulations=sims,
        active_nav="settings",
        active_section="simulation_outlines",
    )


@bp.get("/new")
def new_simulation():
    current_user = _current_user(require_edit=True)
    if isinstance(current_user, Response):
        return current_user
    return render_template(
        "settings_simulations/form.html",
        sim=None,
        active_nav="settings",
        active_section="simulation_outlines",
    )


@bp.post("/new")
def create_simulation():
    current_user = _current_user(require_edit=True)
    if isinstance(current_user, Response):
        return current_user
    number = (request.form.get("number") or "").strip()
    skill = request.form.get("skill") or ""
    descriptor = (request.form.get("descriptor") or "").strip()
    level = request.form.get("level") or ""
    errors: list[str] = []
    if not number or len(number) != 6 or not number.isdigit():
        errors.append("Number must be 6 digits")
    if SimulationOutline.query.filter(func.lower(SimulationOutline.number) == number.lower()).first():
        errors.append("Number must be unique")
    if not descriptor:
        errors.append("Descriptor required")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("settings_simulations.new_simulation"))
    sim = SimulationOutline(number=number, skill=skill, descriptor=descriptor, level=level)
    db.session.add(sim)
    db.session.add(
        AuditLog(user_id=current_user.id, action="simulation_create", details=number)
    )
    db.session.commit()
    flash("Simulation Outline created", "success")
    return redirect(url_for("settings_simulations.list_simulations"))


@bp.get("/<int:sim_id>/edit")
def edit_simulation(sim_id: int):
    current_user = _current_user(require_edit=True)
    if isinstance(current_user, Response):
        return current_user
    sim = db.session.get(SimulationOutline, sim_id)
    if not sim:
        abort(404)
    return render_template(
        "settings_simulations/form.html",
        sim=sim,
        active_nav="settings",
        active_section="simulation_outlines",
    )


@bp.post("/<int:sim_id>/edit")
def update_simulation(sim_id: int):
    current_user = _current_user(require_edit=True)
    if isinstance(current_user, Response):
        return current_user
    sim = db.session.get(SimulationOutline, sim_id)
    if not sim:
        abort(404)
    number = (request.form.get("number") or "").strip()
    skill = request.form.get("skill") or ""
    descriptor = (request.form.get("descriptor") or "").strip()
    level = request.form.get("level") or ""
    errors: list[str] = []
    if not number or len(number) != 6 or not number.isdigit():
        errors.append("Number must be 6 digits")
    existing = SimulationOutline.query.filter(
        func.lower(SimulationOutline.number) == number.lower(),
        SimulationOutline.id != sim.id,
    ).first()
    if existing:
        errors.append("Number must be unique")
    if not descriptor:
        errors.append("Descriptor required")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("settings_simulations.edit_simulation", sim_id=sim.id))
    sim.number = number
    sim.skill = skill
    sim.descriptor = descriptor
    sim.level = level
    db.session.add(
        AuditLog(user_id=current_user.id, action="simulation_update", details=number)
    )
    db.session.commit()
    flash("Simulation Outline updated", "success")
    return redirect(url_for("settings_simulations.list_simulations"))


@bp.post("/<int:sim_id>/delete")
def delete_simulation(sim_id: int):
    current_user = _current_user(require_edit=True)
    if isinstance(current_user, Response):
        return current_user
    sim = db.session.get(SimulationOutline, sim_id)
    if not sim:
        abort(404)
    db.session.delete(sim)
    db.session.add(
        AuditLog(user_id=current_user.id, action="simulation_delete", details=str(sim.id))
    )
    db.session.commit()
    flash("Simulation Outline deleted", "info")
    return redirect(url_for("settings_simulations.list_simulations"))
