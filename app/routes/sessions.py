from __future__ import annotations

import csv
import io
from functools import wraps
from datetime import date, time, datetime, timedelta
import secrets
import hashlib
from zoneinfo import available_timezones, ZoneInfo

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
    current_app,
)

from ..app import db, User
from ..models import (
    Participant,
    ParticipantAccount,
    Client,
    Session,
    SessionParticipant,
    Certificate,
    WorkshopType,
    AuditLog,
    SessionShipping,
    ClientWorkshopLocation,
    SimulationOutline,
    PreworkTemplate,
    PreworkAssignment,
    PreworkEmailLog,
)
from ..shared.time import now_utc, fmt_time, fmt_dt
from sqlalchemy import or_, func
from ..shared.certificates import (
    render_certificate,
    render_for_session,
    remove_session_certificates,
    get_template_mapping,
)
from ..shared.provisioning import (
    deactivate_orphan_accounts_for_session,
    provision_participant_accounts_for_session,
)
from ..shared.constants import MAGIC_LINK_TTL_DAYS, DEFAULT_CSA_PASSWORD
from .. import emailer
from ..shared.rbac import csa_allowed_for_session
from ..shared.accounts import ensure_participant_account
from ..shared.acl import (
    is_admin,
    is_kcrm,
    is_delivery,
    is_contractor,
    is_kt_staff,
    is_sys_admin,
    is_csa_for_session,
    csa_can_manage_participants,
    session_start_dt_utc,
)
from ..shared.languages import get_language_options

bp = Blueprint("sessions", __name__, url_prefix="/sessions")


def _fmt_offset(delta):
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes == 0:
        return "UTC"
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


COMMON_TZ_NAMES = {
    "UTC-10:00": "Hawaii Time",
    "UTC-09:00": "Alaska Time",
    "UTC-08:00": "Pacific Time",
    "UTC-07:00": "Mountain Time",
    "UTC-06:00": "Central Time",
    "UTC-05:00": "Eastern Time",
    "UTC-04:00": "Atlantic Time",
    "UTC": "UTC",
    "UTC+01:00": "Central European Time",
    "UTC+02:00": "Eastern European Time",
    "UTC+03:00": "Moscow Standard Time",
    "UTC+05:30": "India Standard Time",
    "UTC+07:00": "Indochina Time",
    "UTC+08:00": "China Standard Time",
    "UTC+09:00": "Japan Standard Time",
    "UTC+10:00": "Australian Eastern Time",
    "UTC+12:00": "New Zealand Time",
}


def _simple_timezones():
    now = datetime.utcnow()
    seen: dict[int, str] = {}
    for name in sorted(available_timezones()):
        offset = ZoneInfo(name).utcoffset(now)
        if offset is None:
            continue
        seconds = int(offset.total_seconds())
        if seconds not in seen:
            seen[seconds] = _fmt_offset(offset)
    labels: list[str] = []
    for k in sorted(seen):
        offset_str = seen[k]
        label = COMMON_TZ_NAMES.get(offset_str)
        if label and label != "UTC":
            labels.append(f"{label} ({offset_str})")
        else:
            labels.append(label or offset_str)
    return labels


TIMEZONES = _simple_timezones()


def _cb(v) -> bool:
    if v in (True, 1):
        return True
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "y", "yes", "on", "true"}


def _maybe_send_csa_assign(sess: Session, password: str | None = None) -> None:
    if not sess.csa_account_id:
        return
    if sess.csa_account_id == sess.csa_notified_account_id:
        return
    account = db.session.get(ParticipantAccount, sess.csa_account_id)
    if not account or not account.email:
        return
    subject = (
        f"Assigned to Workshop: {sess.workshop_type.name if sess.workshop_type else sess.code}"
        f" ({fmt_dt(sess.start_date)})"
    )
    body = render_template("email/csa_assigned.txt", session=sess, password=password)
    html = render_template("email/csa_assigned.html", session=sess, password=password)
    try:
        result = emailer.send(account.email, subject, body, html)
        if result.get("ok"):
            current_app.logger.info(
                f"[MAIL-OUT] csa-assign session={sess.id} user={account.id} to={account.email} result=sent"
            )
            sess.csa_notified_account_id = account.id
            sess.csa_notified_at = now_utc()
            db.session.commit()
        else:
            current_app.logger.info(
                f"[MAIL-FAIL] csa-assign session={sess.id} user={account.id} to={account.email} error=\"{result.get('detail')}\""
            )
    except Exception as e:  # pragma: no cover - unexpected send error
        current_app.logger.info(
            f'[MAIL-FAIL] csa-assign session={sess.id} user={account.id} to={account.email} error="{e}"'
        )


def staff_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login"))
        user = db.session.get(User, user_id)
        if not user or not (
            is_admin(user) or is_kcrm(user) or is_delivery(user) or is_contractor(user)
        ):
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


@bp.get("")
@staff_required
def list_sessions(current_user):
    show_global = request.args.get("global") == "1"
    params = request.args.to_dict(flat=True)
    base_params = dict(params)
    base_params.pop("sort", None)
    base_params.pop("dir", None)
    flask_session["sessions_list_args"] = params

    query = db.session.query(Session).outerjoin(Client).outerjoin(WorkshopType)
    if not show_global and current_user.region:
        query = query.filter(Session.region == current_user.region)

    q = request.args.get("q")
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Session.title.ilike(like),
                Session.location.ilike(like),
                Client.name.ilike(like),
            )
        )

    status = request.args.get("status")
    if status == "Cancelled":
        query = query.filter(Session.cancelled.is_(True))
    elif status == "On Hold":
        query = query.filter(Session.on_hold.is_(True))
    elif status == "Finalized":
        query = query.filter(Session.finalized.is_(True))
    elif status == "Delivered":
        query = query.filter(Session.delivered.is_(True))
    elif status == "Ready for Delivery":
        query = query.filter(
            Session.ready_for_delivery.is_(True),
            Session.delivered.is_(False),
            Session.finalized.is_(False),
            Session.on_hold.is_(False),
            Session.cancelled.is_(False),
        )
    elif status == "In Progress":
        query = query.filter(
            or_(Session.materials_ordered.is_(True), Session.info_sent.is_(True)),
            Session.ready_for_delivery.is_(False),
            Session.delivered.is_(False),
            Session.finalized.is_(False),
            Session.on_hold.is_(False),
            Session.cancelled.is_(False),
        )
    elif status == "New":
        query = query.filter(
            Session.materials_ordered.is_(False),
            Session.info_sent.is_(False),
            Session.ready_for_delivery.is_(False),
            Session.delivered.is_(False),
            Session.finalized.is_(False),
            Session.on_hold.is_(False),
            Session.cancelled.is_(False),
        )

    region = request.args.get("region")
    if region:
        query = query.filter(Session.region == region)
    delivery_type = request.args.get("delivery_type")
    if delivery_type:
        query = query.filter(Session.delivery_type == delivery_type)
    start_from = request.args.get("start_from")
    if start_from:
        try:
            dt = datetime.strptime(start_from, "%Y-%m-%d").date()
            query = query.filter(Session.start_date >= dt)
        except ValueError:
            pass
    start_to = request.args.get("start_to")
    if start_to:
        try:
            dt = datetime.strptime(start_to, "%Y-%m-%d").date()
            query = query.filter(Session.start_date <= dt)
        except ValueError:
            pass

    sort = request.args.get("sort", "start_date")
    direction = request.args.get("dir", "asc")
    columns = {
        "title": Session.title,
        "client": Client.name,
        "location": Session.location,
        "workshop_type": WorkshopType.name,
        "start_date": Session.start_date,
        "status": None,
        "region": Session.region,
    }
    if sort == "status":
        sessions = query.all()
        sessions.sort(key=lambda s: s.computed_status)
        if direction == "desc":
            sessions.reverse()
    else:
        col = columns.get(sort) or Session.start_date
        if direction == "desc":
            query = query.order_by(col.desc())
        else:
            query = query.order_by(col.asc())
        sessions = query.all()

    return render_template(
        "sessions.html",
        sessions=sessions,
        show_global=show_global,
        params=params,
        base_params=base_params,
        sort=sort,
        direction=direction,
    )


@bp.route("/new", methods=["GET", "POST"])
@staff_required
def new_session(current_user):
    if is_contractor(current_user):
        abort(403)
    workshop_types = WorkshopType.query.order_by(WorkshopType.code).all()
    include_all = request.args.get("include_all_facilitators") == "1"
    fac_query = User.query.filter(
        or_(User.is_kt_delivery == True, User.is_kt_contractor == True)
    )
    if not include_all:
        req_region = request.args.get("region")
        if req_region:
            fac_query = fac_query.filter(User.region == req_region)
    facilitators = fac_query.order_by(User.full_name).all()
    clients = Client.query.order_by(Client.name).all()
    users = User.query.order_by(User.email).all()
    cid_arg = request.args.get("client_id")
    title_arg = request.args.get("title")
    workshop_locations: list[ClientWorkshopLocation] = []
    selected_client_id = None
    if cid_arg and cid_arg.isdigit():
        selected_client_id = int(cid_arg)
        workshop_locations = (
            ClientWorkshopLocation.query.filter_by(
                client_id=selected_client_id, is_active=True
            )
            .order_by(ClientWorkshopLocation.label)
            .all()
        )
    simulation_outlines = SimulationOutline.query.order_by(
        SimulationOutline.number, SimulationOutline.skill
    ).all()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "materials_only":
            missing = []
            title = request.form.get("title")
            if not title:
                missing.append("Title")
            cid = request.form.get("client_id")
            if not cid:
                missing.append("Client")
            region = request.form.get("region")
            if not region:
                missing.append("Region")
            workshop_language = request.form.get("workshop_language")
            if not workshop_language:
                missing.append("Language")
            if workshop_language not in [c for c, _ in get_language_options()]:
                workshop_language = "en"
            if missing:
                flash("Required fields: " + ", ".join(missing), "error")
                return redirect(url_for("sessions.new_session"))
            sess = Session(
                title=title,
                client_id=int(cid) if cid else None,
                region=region,
                workshop_language=workshop_language,
                delivery_type="Material Order",
                start_date=date.today(),
                end_date=date.today(),
                materials_only=True,
            )
            db.session.add(sess)
            db.session.flush()
            db.session.add(
                SessionShipping(session_id=sess.id, created_by=current_user.id)
            )
            db.session.commit()
            return redirect(url_for("materials.materials_view", session_id=sess.id))
        missing = []
        title = request.form.get("title")
        if not title:
            missing.append("Title")
        cid = request.form.get("client_id")
        if not cid:
            missing.append("Client")
        region = request.form.get("region")
        if not region:
            missing.append("Region")
        wt_id = request.form.get("workshop_type_id")
        if not wt_id:
            missing.append("Workshop Type")
        delivery_type = request.form.get("delivery_type")
        if not delivery_type:
            missing.append("Delivery type")
        workshop_language = request.form.get("workshop_language")
        if not workshop_language:
            missing.append("Workshop language")
        if workshop_language not in [c for c, _ in get_language_options()]:
            workshop_language = "en"
        capacity_str = request.form.get("capacity")
        if not capacity_str:
            missing.append("Capacity")
        start_date_str = request.form.get("start_date")
        if not start_date_str:
            missing.append("Start date")
        end_date_str = request.form.get("end_date")
        if not end_date_str:
            missing.append("End date")
        if missing:
            flash("Required fields: " + ", ".join(missing), "error")
            return redirect(url_for("sessions.new_session"))
        wt = db.session.get(WorkshopType, int(wt_id))
        wl_id = request.form.get("workshop_location_id")
        wl = db.session.get(ClientWorkshopLocation, int(wl_id)) if wl_id else None
        start_date_val = date.fromisoformat(start_date_str)
        end_date_val = date.fromisoformat(end_date_str)
        daily_start_str = request.form.get("daily_start_time")
        daily_end_str = request.form.get("daily_end_time")
        daily_start_val = (
            time.fromisoformat(daily_start_str) if daily_start_str else None
        )
        daily_end_val = time.fromisoformat(daily_end_str) if daily_end_str else None
        capacity_val = int(capacity_str)
        materials_ordered = _cb(request.form.get("materials_ordered"))
        ready_for_delivery = _cb(request.form.get("ready_for_delivery"))
        info_sent = _cb(request.form.get("info_sent"))
        delivered = _cb(request.form.get("delivered"))
        finalized = _cb(request.form.get("finalized"))
        no_material_order = action == "no_material"
        so_id = (
            int(request.form.get("simulation_outline_id"))
            if wt and wt.simulation_based and request.form.get("simulation_outline_id")
            else None
        )
        sess = Session(
            title=title,
            start_date=start_date_val,
            end_date=end_date_val,
            daily_start_time=daily_start_val,
            daily_end_time=daily_end_val,
            timezone=request.form.get("timezone") or None,
            location=wl.label if wl else None,
            delivery_type=delivery_type,
            region=region,
            workshop_language=workshop_language,
            capacity=capacity_val,
            materials_ordered=materials_ordered,
            ready_for_delivery=ready_for_delivery,
            info_sent=info_sent,
            delivered=delivered,
            finalized=finalized,
            no_material_order=no_material_order,
            notes=request.form.get("notes") or None,
            simulation_outline_id=so_id,
            client_id=int(cid) if cid else None,
            workshop_location=wl,
        )
        sess.workshop_type = wt
        if wt and workshop_language not in (wt.supported_languages or []):
            flash("Selected workshop type does not support chosen language.", "error")
            return (
                render_template(
                    "sessions/form.html",
                    session=sess,
                    workshop_types=workshop_types,
                    facilitators=facilitators,
                    clients=clients,
                    users=users,
                    workshop_languages=get_language_options(),
                    include_all_facilitators=include_all,
                    participants_count=0,
                    today=date.today(),
                    timezones=TIMEZONES,
                    workshop_locations=workshop_locations,
                    title_override=title_arg,
                    past_warning=False,
                    daily_start_time_str=daily_start_str,
                    daily_end_time_str=daily_end_str,
                    simulation_outlines=simulation_outlines,
                    workshop_type=wt,
                    form=request.form,
                ),
                400,
            )
        participants_count = 0
        if end_date_val < start_date_val:
            flash("End date must be the same day or after the start date.", "error")
            return (
                render_template(
                    "sessions/form.html",
                    session=sess,
                    workshop_types=workshop_types,
                    facilitators=facilitators,
                    clients=clients,
                    users=users,
                    workshop_languages=get_language_options(),
                    include_all_facilitators=include_all,
                    participants_count=participants_count,
                    today=date.today(),
                    timezones=TIMEZONES,
                    workshop_locations=workshop_locations,
                    title_override=title_arg,
                    past_warning=False,
                    daily_start_time_str=daily_start_str,
                    daily_end_time_str=daily_end_str,
                    simulation_outlines=simulation_outlines,
                    workshop_type=wt,
                    form=request.form,
                ),
                400,
            )
        if (
            start_date_val < date.today()
            and request.form.get("ack_past") != start_date_str
        ):
            return (
                render_template(
                    "sessions/form.html",
                    session=sess,
                    workshop_types=workshop_types,
                    facilitators=facilitators,
                    clients=clients,
                    users=users,
                    workshop_languages=get_language_options(),
                    include_all_facilitators=include_all,
                    participants_count=participants_count,
                    today=date.today(),
                    timezones=TIMEZONES,
                    workshop_locations=workshop_locations,
                    title_override=title_arg,
                    past_warning=True,
                    daily_start_time_str=daily_start_str,
                    daily_end_time_str=daily_end_str,
                    simulation_outlines=simulation_outlines,
                    workshop_type=wt,
                    form=request.form,
                ),
                400,
            )
        if finalized:
            delivered = True
            ready_for_delivery = True
        if delivered:
            materials_ordered = True
            info_sent = True
        if ready_for_delivery and participants_count == 0:
            flash("Add participants before marking Ready for delivery.", "error")
            ready_for_delivery = False
        if delivered:
            if not ready_for_delivery:
                flash("Delivered requires 'Ready for delivery' first.", "error")
                delivered = False
            elif end_date_val and end_date_val > date.today():
                flash("Cannot mark Delivered before the end date.", "error")
                delivered = False
        if finalized and not delivered:
            flash("Finalized requires Delivered first.", "error")
            finalized = False
        sess.materials_ordered = materials_ordered
        sess.ready_for_delivery = ready_for_delivery
        sess.info_sent = info_sent
        sess.delivered = delivered
        sess.finalized = finalized
        csa_email = (request.form.get("csa_email") or "").strip().lower()
        csa_password = None
        if csa_email:
            account = (
                db.session.query(ParticipantAccount)
                .filter(func.lower(ParticipantAccount.email) == csa_email)
                .one_or_none()
            )
            if not account:
                user = User.query.filter(func.lower(User.email) == csa_email).first()
                account = ParticipantAccount(
                    email=csa_email,
                    full_name=user.full_name if user else csa_email,
                    is_active=True,
                )
                account.set_password(DEFAULT_CSA_PASSWORD)
                db.session.add(account)
                db.session.flush()
                csa_password = DEFAULT_CSA_PASSWORD
            sess.csa_account_id = account.id
        now = datetime.utcnow()
        if sess.materials_ordered:
            sess.materials_ordered_at = now
        if sess.ready_for_delivery:
            sess.ready_at = now
        if sess.info_sent:
            sess.info_sent_at = now
        if sess.delivered:
            sess.delivered_at = now
        if sess.finalized:
            sess.finalized_at = now
        sess.workshop_type = wt
        lead_id = request.form.get("lead_facilitator_id")
        if lead_id:
            sess.lead_facilitator_id = int(lead_id)
        add_ids = [
            int(fid)
            for fid in request.form.getlist("additional_facilitators")
            if fid and fid != lead_id
        ]
        if add_ids:
            sess.facilitators = User.query.filter(User.id.in_(add_ids)).all()
        db.session.add(sess)
        db.session.flush()
        db.session.add(SessionShipping(session_id=sess.id, created_by=current_user.id))
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=sess.id,
                action="session_create",
                details=f"session_id={sess.id}",
            )
        )
        db.session.commit()
        _maybe_send_csa_assign(sess, password=csa_password)
        if sess.ready_for_delivery:
            summary = provision_participant_accounts_for_session(sess.id)
            total = (
                summary["created"] + summary["reactivated"] + summary["already_active"]
            )
            flash(
                "Provisioned {total} (created {created}, reactivated {reactivated}; skipped staff {skipped_staff}; already active {already_active}).".format(
                    total=total, **summary
                ),
                "success",
            )
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    session_id=sess.id,
                    action="provision",
                    details=(
                        "created={created} skipped={skipped_staff} reactivated={reactivated} already_active={already_active}".format(
                            **summary
                        )
                    ),
                )
            )
            db.session.commit()
        if sess.finalized:
            render_for_session(sess.id)
        changes = []
        if materials_ordered:
            changes.append("Materials ordered")
        if ready_for_delivery:
            changes.append("Ready for delivery")
        if info_sent:
            changes.append("Workshop info sent")
        if delivered:
            changes.append("Delivered")
        if finalized:
            changes.append("Finalized")
        if no_material_order:
            changes.append("No material order")
        msg = "Session saved"
        if changes:
            msg += ": " + ", ".join(changes)
        flash(msg, "success")
        if csa_password:
            flash(
                f"Account created for {csa_email}; password: {csa_password}",
                "success",
            )
        if no_material_order:
            return redirect(url_for("sessions.session_detail", session_id=sess.id))
        return redirect(url_for("materials.materials_view", session_id=sess.id))
    tz_map = {
        "NA": "America/New_York",
        "EU": "Europe/Paris",
        "SEA": "Asia/Singapore",
    }
    tz = tz_map.get(current_user.region, "")
    return render_template(
        "sessions/form.html",
        session=Session(
            title=title_arg,
            daily_start_time=time.fromisoformat("08:00"),
            daily_end_time=time.fromisoformat("17:00"),
            workshop_language="en",
            timezone=tz,
            capacity=16,
            client_id=selected_client_id,
            region=current_user.region,
        ),
        workshop_types=workshop_types,
        facilitators=facilitators,
        clients=clients,
        users=users,
        workshop_languages=get_language_options(),
        include_all_facilitators=include_all,
        participants_count=0,
        today=date.today(),
        timezones=TIMEZONES,
        workshop_locations=workshop_locations,
        title_override=title_arg,
        past_warning=False,
        daily_start_time_str="08:00",
        daily_end_time_str="17:00",
        simulation_outlines=simulation_outlines,
        workshop_type=None,
        form=None,
    )


@bp.route("/<int:session_id>/edit", methods=["GET", "POST"])
@staff_required
def edit_session(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    if is_contractor(current_user):
        abort(403)
    workshop_types = WorkshopType.query.order_by(WorkshopType.code).all()
    include_all = request.args.get("include_all_facilitators") == "1"
    fac_query = User.query.filter(
        or_(User.is_kt_delivery == True, User.is_kt_contractor == True)
    )
    if not include_all and sess.region:
        fac_query = fac_query.filter(User.region == sess.region)
    facilitators = fac_query.order_by(User.full_name).all()
    clients = Client.query.order_by(Client.name).all()
    title_arg = request.args.get("title")
    simulation_outlines = SimulationOutline.query.order_by(
        SimulationOutline.number, SimulationOutline.skill
    ).all()
    participants_count = (
        db.session.query(SessionParticipant).filter_by(session_id=sess.id).count()
    )
    workshop_locations = (
        ClientWorkshopLocation.query.filter_by(client_id=sess.client_id, is_active=True)
        .order_by(ClientWorkshopLocation.label)
        .all()
        if sess.client_id
        else []
    )
    if request.method == "POST":
        old_ready = bool(sess.ready_for_delivery)
        ready_present = "ready_for_delivery" in request.form
        new_ready = _cb(request.form.get("ready_for_delivery"))
        if not ready_present:
            new_ready = old_ready
        wt_id = request.form.get("workshop_type_id")
        if wt_id:
            sess.workshop_type = db.session.get(WorkshopType, int(wt_id))
        else:
            sess.workshop_type = None
        old_delivered = sess.delivered
        old_materials = sess.materials_ordered
        old_info = sess.info_sent
        old_finalized = sess.finalized
        old_on_hold = sess.on_hold
        old_no_material = sess.no_material_order
        sess.title = request.form.get("title")
        start_date_str = request.form.get("start_date")
        start_date_val = date.fromisoformat(start_date_str) if start_date_str else None
        old_start = sess.start_date
        sess.start_date = start_date_val
        end_date_str = request.form.get("end_date")
        end_date_val = date.fromisoformat(end_date_str) if end_date_str else None
        sess.end_date = end_date_val
        daily_start_str = request.form.get("daily_start_time")
        daily_end_str = request.form.get("daily_end_time")
        sess.daily_start_time = (
            time.fromisoformat(daily_start_str) if daily_start_str else None
        )
        sess.daily_end_time = (
            time.fromisoformat(daily_end_str) if daily_end_str else None
        )
        sess.timezone = request.form.get("timezone") or None
        sess.workshop_location_id = (
            int(request.form.get("workshop_location_id"))
            if request.form.get("workshop_location_id")
            else None
        )
        sess.location = sess.workshop_location.label if sess.workshop_location else None
        sess.delivery_type = request.form.get("delivery_type") or None
        sess.region = request.form.get("region") or None
        wl_val = request.form.get("workshop_language")
        if wl_val in [c for c, _ in get_language_options()]:
            sess.workshop_language = wl_val
        if sess.workshop_type and sess.workshop_language not in (
            sess.workshop_type.supported_languages or []
        ):
            flash("Selected workshop type does not support chosen language.", "error")
            return (
                render_template(
                    "sessions/form.html",
                    session=sess,
                    workshop_types=workshop_types,
                    facilitators=facilitators,
                    clients=clients,
                    workshop_languages=get_language_options(),
                    include_all_facilitators=include_all,
                    participants_count=participants_count,
                    today=date.today(),
                    timezones=TIMEZONES,
                    workshop_locations=workshop_locations,
                    title_override=title_arg,
                    past_warning=False,
                    daily_start_time_str=daily_start_str,
                    daily_end_time_str=daily_end_str,
                    simulation_outlines=simulation_outlines,
                    workshop_type=sess.workshop_type,
                    form=request.form,
                ),
                400,
            )
        sess.capacity = request.form.get("capacity") or None
        if start_date_val and end_date_val and end_date_val < start_date_val:
            flash("End date must be the same day or after the start date.", "error")
            return (
                render_template(
                    "sessions/form.html",
                    session=sess,
                    workshop_types=workshop_types,
                    facilitators=facilitators,
                    clients=clients,
                    workshop_languages=get_language_options(),
                    include_all_facilitators=include_all,
                    participants_count=participants_count,
                    today=date.today(),
                    timezones=TIMEZONES,
                    workshop_locations=workshop_locations,
                    title_override=title_arg,
                    past_warning=False,
                    daily_start_time_str=daily_start_str,
                    daily_end_time_str=daily_end_str,
                    simulation_outlines=simulation_outlines,
                    workshop_type=sess.workshop_type,
                    form=request.form,
                ),
                400,
            )
        if (
            start_date_val
            and start_date_val < date.today()
            and (not old_start or start_date_val != old_start)
            and request.form.get("ack_past") != start_date_str
        ):
            return (
                render_template(
                    "sessions/form.html",
                    session=sess,
                    workshop_types=workshop_types,
                    facilitators=facilitators,
                    clients=clients,
                    workshop_languages=get_language_options(),
                    include_all_facilitators=include_all,
                    participants_count=participants_count,
                    today=date.today(),
                    timezones=TIMEZONES,
                    workshop_locations=workshop_locations,
                    title_override=title_arg,
                    past_warning=True,
                    daily_start_time_str=daily_start_str,
                    daily_end_time_str=daily_end_str,
                    simulation_outlines=simulation_outlines,
                    workshop_type=sess.workshop_type,
                    form=request.form,
                ),
                400,
            )
        materials_ordered = (
            _cb(request.form.get("materials_ordered"))
            if "materials_ordered" in request.form
            else old_materials
        )
        info_sent = (
            _cb(request.form.get("info_sent"))
            if "info_sent" in request.form
            else old_info
        )
        delivered = (
            _cb(request.form.get("delivered"))
            if "delivered" in request.form
            else old_delivered
        )
        finalized = (
            _cb(request.form.get("finalized"))
            if "finalized" in request.form
            else old_finalized
        )
        on_hold = (
            _cb(request.form.get("on_hold"))
            if "on_hold" in request.form
            else old_on_hold
        )
        no_material_order = (
            _cb(request.form.get("no_material_order"))
            if "no_material_order" in request.form
            else old_no_material
        )
        if finalized:
            delivered = True
            new_ready = True
        if delivered:
            materials_ordered = True
            info_sent = True
        if new_ready and participants_count == 0:
            flash("Add participants before marking Ready for delivery.", "error")
            new_ready = False
        if delivered:
            if not new_ready:
                flash("Delivered requires 'Ready for delivery' first.", "error")
                delivered = False
            elif sess.end_date and sess.end_date > date.today():
                flash("Cannot mark Delivered before the end date.", "error")
                delivered = False
        if finalized and not delivered:
            flash("Finalized requires Delivered first.", "error")
            finalized = False
        sess.materials_ordered = materials_ordered
        sess.ready_for_delivery = new_ready or delivered
        sess.info_sent = info_sent
        sess.delivered = delivered
        sess.finalized = finalized
        sess.on_hold = on_hold
        sess.no_material_order = no_material_order
        sess.notes = request.form.get("notes") or None
        if sess.workshop_type and sess.workshop_type.simulation_based:
            so_id = request.form.get("simulation_outline_id")
            sess.simulation_outline_id = int(so_id) if so_id else None
        else:
            sess.simulation_outline_id = None
        cid = request.form.get("client_id")
        sess.client_id = int(cid) if cid else None
        csa_email = (request.form.get("csa_email") or "").strip().lower()
        csa_password = None
        if csa_email:
            account = (
                db.session.query(ParticipantAccount)
                .filter(func.lower(ParticipantAccount.email) == csa_email)
                .one_or_none()
            )
            if not account:
                user = User.query.filter(func.lower(User.email) == csa_email).first()
                account = ParticipantAccount(
                    email=csa_email,
                    full_name=user.full_name if user else csa_email,
                    is_active=True,
                )
                account.set_password(DEFAULT_CSA_PASSWORD)
                db.session.add(account)
                db.session.flush()
                csa_password = DEFAULT_CSA_PASSWORD
            sess.csa_account_id = account.id
        else:
            sess.csa_account_id = None
            sess.csa_notified_account_id = None
            sess.csa_notified_at = None
        lead_id = request.form.get("lead_facilitator_id")
        sess.lead_facilitator_id = int(lead_id) if lead_id else None
        add_ids = [
            int(fid)
            for fid in request.form.getlist("additional_facilitators")
            if fid and fid != lead_id
        ]
        sess.facilitators = (
            User.query.filter(User.id.in_(add_ids)).all() if add_ids else []
        )
        now = datetime.utcnow()
        flag_changes = []
        if materials_ordered != old_materials:
            flag_changes.append(("materials_ordered", old_materials, materials_ordered))
            if materials_ordered and not sess.materials_ordered_at:
                sess.materials_ordered_at = now
        if new_ready != old_ready:
            flag_changes.append(("ready_for_delivery", old_ready, new_ready))
            if new_ready and not sess.ready_at:
                sess.ready_at = now
        if info_sent != old_info:
            flag_changes.append(("info_sent", old_info, info_sent))
            if info_sent and not sess.info_sent_at:
                sess.info_sent_at = now
        if delivered != old_delivered:
            flag_changes.append(("delivered", old_delivered, delivered))
            if delivered and not sess.delivered_at:
                sess.delivered_at = now
        if finalized != old_finalized:
            flag_changes.append(("finalized", old_finalized, finalized))
            if finalized and not sess.finalized_at:
                sess.finalized_at = now
        if on_hold != old_on_hold:
            flag_changes.append(("on_hold", old_on_hold, on_hold))
            if on_hold and not sess.on_hold_at:
                sess.on_hold_at = now
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=sess.id,
                action="session_update",
                details=f"session_id={sess.id}",
            )
        )
        for flag, old, new in flag_changes:
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    session_id=sess.id,
                    action="lifecycle_flip",
                    details=f"{flag}:{old}->{new}",
                )
            )
        db.session.commit()
        _maybe_send_csa_assign(sess, password=csa_password)
        if new_ready and not old_ready:
            summary = provision_participant_accounts_for_session(sess.id)
            total = (
                summary["created"] + summary["reactivated"] + summary["already_active"]
            )
            flash(
                "Provisioned {total} (created {created}, reactivated {reactivated}; skipped staff {skipped_staff}; already active {already_active}).".format(
                    total=total, **summary
                ),
                "success",
            )
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    session_id=sess.id,
                    action="provision",
                    details=(
                        "created={created} skipped={skipped_staff} reactivated={reactivated} already_active={already_active}".format(
                            **summary
                        )
                    ),
                )
            )
            db.session.commit()
        if finalized and not old_finalized:
            render_for_session(sess.id)
        if sess.cancelled or sess.on_hold:
            deactivated = deactivate_orphan_accounts_for_session(sess.id)
            if deactivated:
                db.session.add(
                    AuditLog(
                        user_id=current_user.id,
                        session_id=sess.id,
                        action="deactivate",
                        details=f"count={deactivated}",
                    )
                )
                db.session.commit()
        changes = []
        if materials_ordered != old_materials:
            changes.append(
                "Materials ordered " + ("on" if materials_ordered else "off")
            )
        if new_ready != old_ready:
            changes.append("Ready for delivery " + ("on" if new_ready else "off"))
        if info_sent != old_info:
            changes.append("Workshop info sent " + ("on" if info_sent else "off"))
        if delivered != old_delivered:
            changes.append("Delivered " + ("on" if delivered else "off"))
        if finalized != old_finalized:
            changes.append("Finalized " + ("on" if finalized else "off"))
        if no_material_order != old_no_material:
            changes.append(
                "No material order " + ("on" if no_material_order else "off")
            )
        msg = "Session saved"
        if changes:
            msg += ": " + ", ".join(changes)
        flash(msg, "success")
        if csa_password:
            flash(
                f"Account created for {csa_email}; password: {csa_password}",
                "success",
            )
        return redirect(url_for("sessions.session_detail", session_id=sess.id))
    return render_template(
        "sessions/form.html",
        session=sess,
        workshop_types=workshop_types,
        facilitators=facilitators,
        clients=clients,
        workshop_languages=get_language_options(),
        include_all_facilitators=include_all,
        participants_count=participants_count,
        today=date.today(),
        timezones=TIMEZONES,
        workshop_locations=workshop_locations,
        title_override=title_arg,
        past_warning=False,
        daily_start_time_str=fmt_time(sess.daily_start_time),
        daily_end_time_str=fmt_time(sess.daily_end_time),
        simulation_outlines=simulation_outlines,
        workshop_type=sess.workshop_type,
        form=None,
    )


@bp.get("/<int:session_id>")
@csa_allowed_for_session(allow_delivered_view=True)
def session_detail(session_id: int, sess, current_user, csa_view, csa_account):
    view_csa = csa_view or request.args.get("view") == "csa"
    participants: list[dict[str, object]] = []
    import_errors = None
    can_manage = False
    start_dt_utc = session_start_dt_utc(sess)
    back_params = flask_session.get("sessions_list_args", {})
    badge_filename = None
    if not sess.materials_only:
        rows = (
            db.session.query(SessionParticipant, Participant, Certificate.pdf_path)
            .join(Participant, SessionParticipant.participant_id == Participant.id)
            .outerjoin(
                Certificate,
                (Certificate.session_id == session_id)
                & (Certificate.participant_id == Participant.id),
            )
            .filter(SessionParticipant.session_id == session_id)
            .all()
        )
        participants = [
            {"participant": participant, "link": link, "pdf_path": pdf_path}
            for link, participant, pdf_path in rows
        ]
        import_errors = flask_session.pop("import_errors", None)
        if csa_account:
            can_manage = csa_can_manage_participants(csa_account, sess)
        mapping, _ = get_template_mapping(sess)
        if mapping:
            badge_filename = mapping.badge_filename
    return render_template(
        "session_detail.html",
        session=sess,
        participants=participants,
        import_errors=import_errors,
        csa_view=view_csa,
        current_user=current_user,
        csa_can_manage=can_manage,
        session_start_dt=start_dt_utc,
        back_params=back_params,
        badge_filename=badge_filename,
    )


@bp.post("/<int:session_id>/assign-csa")
@staff_required
def assign_csa(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    email = (request.form.get("email") or "").strip().lower()
    if not email:
        flash("Email required", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    account = (
        db.session.query(ParticipantAccount)
        .filter(func.lower(ParticipantAccount.email) == email)
        .one_or_none()
    )
    password = None
    if not account:
        user = User.query.filter(func.lower(User.email) == email).first()
        account = ParticipantAccount(
            email=email,
            full_name=user.full_name if user else email,
            is_active=True,
        )
        account.set_password(DEFAULT_CSA_PASSWORD)
        db.session.add(account)
        db.session.flush()
        password = DEFAULT_CSA_PASSWORD
    sess.csa_account_id = account.id
    db.session.commit()
    _maybe_send_csa_assign(sess, password=password)
    flash("CSA assigned", "success")
    if password:
        flash(
            f"Account created for {account.email}; password: {password}",
            "success",
        )
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/remove-csa")
@staff_required
def remove_csa(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    sess.csa_account_id = None
    sess.csa_notified_account_id = None
    sess.csa_notified_at = None
    db.session.commit()
    flash("CSA removed", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/cancel")
@staff_required
def cancel_session(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    if not sess.cancelled:
        sess.cancelled = True
        if not sess.cancelled_at:
            sess.cancelled_at = datetime.utcnow()
        remove_session_certificates(session_id, sess.end_date)
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=session_id,
                action="lifecycle_flip",
                details="cancelled:False->True",
            )
        )
        db.session.commit()
        deactivate_orphan_accounts_for_session(sess.id)
    flash("Session cancelled", "warning")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/finalize")
@staff_required
def finalize_session(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    if not sess.delivered:
        flash("Finalized requires Delivered first.", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    if not sess.finalized:
        sess.finalized = True
        if not sess.finalized_at:
            sess.finalized_at = datetime.utcnow()
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=session_id,
                action="lifecycle_flip",
                details="finalized:False->True",
            )
        )
        db.session.commit()
        render_for_session(session_id)
    flash("Session finalized", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/delete")
@staff_required
def delete_session(session_id: int, current_user):
    if not is_sys_admin(current_user):
        abort(403)
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    if not sess.cancelled:
        flash("Only cancelled sessions can be deleted.", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    remove_session_certificates(session_id, sess.end_date)
    db.session.delete(sess)
    db.session.commit()
    flash("Session deleted", "success")
    return redirect(url_for("sessions.list_sessions"))


@bp.post("/<int:session_id>/participants/add")
@csa_allowed_for_session
def add_participant(session_id: int, sess, current_user, csa_view, csa_account):
    allowed = False
    if current_user and (
        is_admin(current_user)
        or is_kcrm(current_user)
        or is_delivery(current_user)
        or is_contractor(current_user)
    ):
        allowed = True
    elif csa_can_manage_participants(csa_account, sess):
        current_app.logger.info(
            f"[CSA] manage-participants allowed user={csa_account.id} session={sess.id}"
        )
        allowed = True
    else:
        if is_csa_for_session(csa_account, sess):
            current_app.logger.info(
                f"[CSA] manage-participants blocked-after-ready user={csa_account.id} session={sess.id}"
            )
        abort(403)
    if sess.participants_locked():
        flash("Participants are locked for this session.", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    email = (request.form.get("email") or "").strip().lower()
    full_name = (request.form.get("full_name") or "").strip()
    title = (request.form.get("title") or "").strip()
    if not email:
        flash("Email required", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    user = User.query.filter(func.lower(User.email) == email).first()
    participant = (
        db.session.query(Participant)
        .filter(db.func.lower(Participant.email) == email)
        .one_or_none()
    )
    if not participant:
        participant = Participant(
            email=email,
            full_name=full_name or (user.full_name if user else ""),
            title=title or (user.title if user else None),
        )
        db.session.add(participant)
        db.session.flush()
    else:
        if full_name:
            participant.full_name = full_name
        elif user and user.full_name and not participant.full_name:
            participant.full_name = user.full_name
        if title:
            participant.title = title
        elif user and user.title and not participant.title:
            participant.title = user.title
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant.id)
        .one_or_none()
    )
    if not link:
        link = SessionParticipant(
            session_id=session_id,
            participant_id=participant.id,
            completion_date=sess.end_date,
        )
        db.session.add(link)
    account = (
        db.session.query(ParticipantAccount)
        .filter(db.func.lower(ParticipantAccount.email) == email)
        .one_or_none()
    )
    if not account:
        base_name = full_name or (user.full_name if user else "")
        account = ParticipantAccount(
            email=email,
            full_name=base_name,
            certificate_name=base_name,
            is_active=True,
        )
        db.session.add(account)
        db.session.flush()
    else:
        if full_name:
            account.full_name = full_name
            if not account.certificate_name:
                account.certificate_name = full_name
        elif user and user.full_name and not account.full_name:
            account.full_name = user.full_name
            if not account.certificate_name:
                account.certificate_name = user.full_name
    participant.account_id = account.id
    db.session.add(
        AuditLog(
            user_id=current_user.id if current_user else None,
            session_id=session_id,
            participant_id=participant.id,
            action="participant_add",
            details="CSA added 1 participant" if current_user is None else None,
        )
    )
    db.session.commit()
    if sess.ready_for_delivery:
        summary = provision_participant_accounts_for_session(sess.id)
        total = summary["created"] + summary["reactivated"] + summary["already_active"]
        if total:
            flash(
                "Provisioned {total} (created {created}, reactivated {reactivated}; skipped staff {skipped_staff}; already active {already_active}).".format(
                    total=total, **summary
                ),
                "success",
            )
    flash("Participant added", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.route(
    "/<int:session_id>/participants/<int:participant_id>/edit", methods=["GET", "POST"]
)
@csa_allowed_for_session
def edit_participant(
    session_id: int, participant_id: int, sess, current_user, csa_view, csa_account
):
    if not (
        current_user
        and (
            is_admin(current_user)
            or is_kcrm(current_user)
            or is_delivery(current_user)
            or is_contractor(current_user)
        )
        or csa_can_manage_participants(csa_account, sess)
    ):
        abort(403)
    if sess.participants_locked():
        flash("Participants are locked for this session.", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant_id)
        .one_or_none()
    )
    if not link:
        abort(404)
    participant = db.session.get(Participant, participant_id)
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        title = (request.form.get("title") or "").strip()
        participant.full_name = full_name or None
        participant.title = title or None
        db.session.commit()
        flash("Participant updated", "success")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    return render_template(
        "participant_edit.html", session_id=session_id, participant=participant
    )


@bp.post("/<int:session_id>/participants/<int:participant_id>/remove")
@csa_allowed_for_session
def remove_participant(
    session_id: int, participant_id: int, sess, current_user, csa_view, csa_account
):
    if current_user and (
        is_admin(current_user)
        or is_kcrm(current_user)
        or is_delivery(current_user)
        or is_contractor(current_user)
    ):
        pass
    elif csa_can_manage_participants(csa_account, sess):
        current_app.logger.info(
            f"[CSA] manage-participants allowed user={csa_account.id} session={sess.id}"
        )
    else:
        if is_csa_for_session(csa_account, sess):
            current_app.logger.info(
                f"[CSA] manage-participants blocked-after-ready user={csa_account.id} session={sess.id}"
            )
        abort(403)
    if sess.participants_locked():
        flash("Participants are locked for this session.", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant_id)
        .one_or_none()
    )
    if link:
        db.session.delete(link)
        db.session.commit()
        flash("Participant removed", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.get("/<int:session_id>/participants/sample-csv")
@staff_required
def sample_csv(session_id: int, current_user):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["FullName", "Email", "Title"])
    writer.writerow(["Jane Doe", "jane@example.com", "Manager"])
    writer.writerow(["John Smith", "john@example.com", "Director"])
    resp = Response(output.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=sample.csv"
    return resp


@bp.post("/<int:session_id>/participants/import-csv")
@csa_allowed_for_session
def import_csv(session_id: int, sess, current_user, csa_view, csa_account):
    if current_user and (
        is_admin(current_user)
        or is_kcrm(current_user)
        or is_delivery(current_user)
        or is_contractor(current_user)
    ):
        pass
    elif csa_can_manage_participants(csa_account, sess):
        current_app.logger.info(
            f"[CSA] manage-participants allowed user={csa_account.id} session={sess.id}"
        )
    else:
        if is_csa_for_session(csa_account, sess):
            current_app.logger.info(
                f"[CSA] manage-participants blocked-after-ready user={csa_account.id} session={sess.id}"
            )
        abort(403)
    if sess.participants_locked():
        flash("Participants are locked for this session.", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    file = request.files.get("file")
    if not file or not file.filename.endswith(".csv"):
        flash("CSV file required", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    text = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    errors: list[str] = []
    for idx, row in enumerate(reader, start=2):
        full_name = (row.get("FullName") or "").strip()
        email = (row.get("Email") or "").strip().lower()
        title = (row.get("Title") or "").strip()
        if not email or "@" not in email:
            errors.append(f"Row {idx}: invalid email '{email}'")
            continue
        participant = (
            db.session.query(Participant)
            .filter(func.lower(Participant.email) == email)
            .one_or_none()
        )
        if not participant:
            participant = Participant(
                email=email, full_name=full_name or None, title=title or None
            )
            db.session.add(participant)
            db.session.flush()
        else:
            if full_name:
                participant.full_name = full_name
            if title:
                participant.title = title
        link = (
            db.session.query(SessionParticipant)
            .filter_by(session_id=session_id, participant_id=participant.id)
            .one_or_none()
        )
        if not link:
            link = SessionParticipant(
                session_id=session_id,
                participant_id=participant.id,
                completion_date=sess.end_date,
            )
            db.session.add(link)
        imported += 1
    db.session.add(
        AuditLog(
            user_id=current_user.id if current_user else None,
            session_id=session_id,
            action="participant_import",
            details=(
                "CSA added {n} participants".format(n=imported)
                if current_user is None
                else None
            ),
        )
    )
    db.session.commit()
    if sess.ready_for_delivery:
        summary = provision_participant_accounts_for_session(sess.id)
        total = summary["created"] + summary["reactivated"] + summary["already_active"]
        if total:
            flash(
                "Provisioned {total} (created {created}, reactivated {reactivated}; skipped staff {skipped_staff}; already active {already_active}).".format(
                    total=total, **summary
                ),
                "success",
            )
    flask_session["import_errors"] = errors
    flash(f"Imported {imported}, skipped {len(errors)}", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/participants/<int:participant_id>/generate")
@staff_required
def generate_single(session_id: int, participant_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    if not sess.delivered or sess.cancelled:
        flash("Delivered required before generating certificates", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant_id)
        .one_or_none()
    )
    if not link:
        abort(404)
    action = request.form.get("action")
    if "completion_date" in request.form:
        link.completion_date = request.form.get("completion_date") or None
        db.session.commit()
    if action == "generate":
        participant = db.session.get(Participant, participant_id)
        if participant and participant.account:
            render_certificate(sess, participant.account)
            flash("Certificate generated", "success")
        else:
            flash("No participant account", "error")
    else:
        flash("Participant updated", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/generate")
@staff_required
def generate_bulk(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    if not sess.delivered or sess.cancelled:
        flash("Delivered required before generating certificates", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    count, _ = render_for_session(session_id)
    flash(f"Generated {count} certificates", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.route("/<int:session_id>/prework", methods=["GET", "POST"])
def session_prework(session_id: int):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    user_id = flask_session.get("user_id")
    account_id = flask_session.get("participant_account_id")
    if account_id and not user_id:
        if sess.csa_account_id == int(account_id):
            flash("CSA cannot send prework", "error")
        return Response("", 403)
    if not user_id:
        return redirect(url_for("auth.login"))
    current_user = db.session.get(User, user_id)
    if not current_user:
        abort(403)
    if is_contractor(current_user):
        if not (
            sess.lead_facilitator_id == current_user.id
            or any(f.id == current_user.id for f in sess.facilitators)
        ):
            abort(403)
    elif not is_kt_staff(current_user):
        abort(403)
    template = PreworkTemplate.query.filter_by(
        workshop_type_id=sess.workshop_type_id, is_active=True
    ).first()
    participants = (
        db.session.query(Participant, ParticipantAccount)
        .join(SessionParticipant, SessionParticipant.participant_id == Participant.id)
        .outerjoin(ParticipantAccount, Participant.account_id == ParticipantAccount.id)
        .filter(SessionParticipant.session_id == sess.id)
        .order_by(Participant.full_name)
        .all()
    )
    if request.method == "POST":
        action = request.form.get("action")
        account_cache: dict[str, ParticipantAccount] = {}

        def prepare_assignment(account: ParticipantAccount) -> PreworkAssignment | None:
            if not template:
                return None
            assignment = PreworkAssignment.query.filter_by(
                session_id=sess.id, participant_account_id=account.id
            ).first()
            if not assignment:
                snapshot = {
                    "questions": [
                        {
                            "index": idx,
                            "text": q.text,
                            "required": q.required,
                            "kind": q.kind,
                            "min_items": q.min_items,
                            "max_items": q.max_items,
                        }
                        for idx, q in enumerate(
                            sorted(template.questions, key=lambda q: q.position),
                            start=1,
                        )
                    ],
                    "resources": [r.resource_id for r in template.resources],
                }
                due_at = None
                if sess.start_date and sess.daily_start_time:
                    due_at = datetime.combine(
                        sess.start_date, sess.daily_start_time
                    ) - timedelta(days=3)
                assignment = PreworkAssignment(
                    session_id=sess.id,
                    participant_account_id=account.id,
                    template_id=template.id,
                    status="PENDING",
                    due_at=due_at,
                    snapshot_json=snapshot,
                )
                db.session.add(assignment)
            return assignment

        def send_mail(
            assignment: PreworkAssignment,
            account: ParticipantAccount,
            temp_password: str | None,
        ) -> bool:
            token = secrets.token_urlsafe(16)
            assignment.magic_token_hash = hashlib.sha256(
                (token + current_app.secret_key).encode()
            ).hexdigest()
            assignment.magic_token_expires = now_utc() + timedelta(
                days=MAGIC_LINK_TTL_DAYS
            )
            db.session.flush()
            link = url_for(
                "auth.prework_magic",
                assignment_id=assignment.id,
                token=token,
                _external=True,
                _scheme="https",
            )
            subject = f"Prework for Workshop: {sess.title}"
            body = render_template(
                "email/prework.txt",
                session=sess,
                assignment=assignment,
                link=link,
                account=account,
                temp_password=temp_password,
            )
            html_body = render_template(
                "email/prework.html",
                session=sess,
                assignment=assignment,
                link=link,
                account=account,
                temp_password=temp_password,
            )
            try:
                res = emailer.send(account.email, subject, body, html=html_body)
            except Exception as e:  # pragma: no cover - defensive
                res = {"ok": False, "detail": str(e)}
            if res.get("ok"):
                assignment.status = "SENT"
                assignment.sent_at = now_utc()
                db.session.add(
                    PreworkEmailLog(
                        assignment_id=assignment.id,
                        to_email=account.email,
                        subject=subject,
                    )
                )
                current_app.logger.info(
                    f'[MAIL-OUT] prework session={sess.id} pa={account.id} to={account.email} subject="{subject}"'
                )
                return True
            current_app.logger.info(
                f"[MAIL-FAIL] prework session={sess.id} pa={account.id} to={account.email} error=\"{res.get('detail')}\""
            )
            return False

        if action == "toggle_no_prework":
            sess.no_prework = _cb(request.form.get("no_prework"))
            assignments = PreworkAssignment.query.filter_by(session_id=sess.id).all()
            for a in assignments:
                if sess.no_prework:
                    a.status = "WAIVED"
                    a.sent_at = None
                    a.magic_token_hash = None
                    a.magic_token_expires = None
                else:
                    if a.status == "WAIVED":
                        a.status = "PENDING"
            db.session.commit()
            current_app.logger.info(
                f"[SESS] no_prework={sess.no_prework} session={sess.id}"
            )
            flash(
                (
                    "Prework disabled for this workshop"
                    if sess.no_prework
                    else "Prework enabled"
                ),
                "info",
            )
            return redirect(url_for("sessions.session_prework", session_id=session_id))

        if action == "send_accounts":
            any_fail = False
            for p, _ in participants:
                try:
                    account, temp_password = ensure_participant_account(
                        p, account_cache
                    )
                except ValueError:
                    continue
                assignment = prepare_assignment(account)
                token = secrets.token_urlsafe(16)
                account.login_magic_hash = hashlib.sha256(
                    (token + current_app.secret_key).encode()
                ).hexdigest()
                account.login_magic_expires = now_utc() + timedelta(
                    days=MAGIC_LINK_TTL_DAYS
                )
                db.session.flush()
                link = url_for(
                    "auth.account_magic",
                    account_id=account.id,
                    token=token,
                    _external=True,
                    _scheme="https",
                )
                subject = f"Workshop Portal Access: {sess.title}"
                body = render_template(
                    "email/account_invite.txt",
                    session=sess,
                    link=link,
                    account=account,
                    temp_password=temp_password,
                )
                html_body = render_template(
                    "email/account_invite.html",
                    session=sess,
                    link=link,
                    account=account,
                    temp_password=temp_password,
                )
                try:
                    res = emailer.send(account.email, subject, body, html=html_body)
                except Exception as e:  # pragma: no cover - defensive
                    res = {"ok": False, "detail": str(e)}
                if res.get("ok"):
                    if assignment:
                        assignment.account_sent_at = now_utc()
                    current_app.logger.info(
                        f"[MAIL-OUT] account-invite session={sess.id} pa={account.id} to={account.email}"
                    )
                else:
                    any_fail = True
            db.session.commit()
            if any_fail:
                flash("Some emails failed; check logs", "error")
            else:
                flash("Account links sent", "success")
            return redirect(url_for("sessions.session_prework", session_id=session_id))

        if action == "resend":
            pid = int(request.form.get("participant_id"))
            participant = db.session.get(Participant, pid)
            account, temp_password = ensure_participant_account(
                participant, account_cache
            )
            assignment = prepare_assignment(account)
            if assignment and assignment.status == "WAIVED":
                flash("Participant is waived", "error")
                return redirect(
                    url_for("sessions.session_prework", session_id=session_id)
                )
            if assignment:
                send_mail(assignment, account, temp_password)
            db.session.commit()
            return redirect(url_for("sessions.session_prework", session_id=session_id))

        if action == "send_all":
            if sess.no_prework:
                flash("Prework disabled for this workshop", "error")
                return redirect(
                    url_for("sessions.session_prework", session_id=session_id)
                )
            if not template:
                flash("No active prework template", "error")
                return redirect(
                    url_for("sessions.session_prework", session_id=session_id)
                )
            any_fail = False
            for p, _ in participants:
                try:
                    account, temp_password = ensure_participant_account(
                        p, account_cache
                    )
                except ValueError:
                    continue
                assignment = prepare_assignment(account)
                if assignment and assignment.status == "WAIVED":
                    continue
                if assignment and not send_mail(assignment, account, temp_password):
                    any_fail = True
            db.session.commit()
            if any_fail:
                flash("Some emails failed; check logs", "error")
            else:
                flash("Prework assignments sent", "success")
            return redirect(url_for("sessions.session_prework", session_id=session_id))

        flash("Unknown action", "error")
        return redirect(url_for("sessions.session_prework", session_id=session_id))
    rows = []
    any_assignment = False
    for p, account in participants:
        assignment = None
        if account:
            assignment = PreworkAssignment.query.filter_by(
                session_id=sess.id, participant_account_id=account.id
            ).first()
        if assignment:
            any_assignment = True
        rows.append((p, account, assignment))
    return render_template(
        "sessions/prework.html",
        session=sess,
        rows=rows,
        template=template,
        any_assignment=any_assignment,
    )
