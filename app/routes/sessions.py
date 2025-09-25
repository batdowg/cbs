from __future__ import annotations

import csv
import io
import os
import zipfile
from urllib.parse import urlparse
from collections import defaultdict
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
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
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
    ParticipantAttendance,
    WorkshopType,
    AuditLog,
    SessionShipping,
    MaterialOrderItem,
    ClientWorkshopLocation,
    SimulationOutline,
    PreworkTemplate,
    PreworkAssignment,
    PreworkEmailLog,
    Settings,
)
from ..shared.time import now_utc, fmt_time, fmt_dt
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload, selectinload
from ..shared.certificates import (
    CertificateAttendanceError,
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
from ..shared.names import combine_first_last, split_full_name, greeting_name
from ..shared.sessions_lifecycle import (
    enforce_material_only_rules,
    is_certificate_only_session,
    is_material_only,
    is_material_only_session,
)

MATERIALS_OUTSTANDING_MESSAGE = "There are still material order items outstanding"


def _material_order_status(session_id: int) -> tuple[bool, bool]:
    items = MaterialOrderItem.query.filter_by(session_id=session_id).all()
    if not items:
        return False, True
    return True, all(item.processed for item in items)
from ..shared.prework_summary import get_session_prework_summary
from ..shared.prework_status import (
    ParticipantPreworkStatus,
    get_participant_prework_status,
    summarize_prework_status,
)
from ..services.prework_invites import (
    PreworkSendError,
    send_prework_invites,
)
from ..services.attendance import (
    AttendanceForbiddenError,
    AttendanceValidationError,
    mark_all_attended,
    upsert_attendance,
)

bp = Blueprint("sessions", __name__, url_prefix="/sessions")


def _user_can_edit_session(user: User | None) -> bool:
    return bool(
        user
        and (
            is_admin(user)
            or is_kcrm(user)
            or is_delivery(user)
            or is_contractor(user)
        )
    )


def _redirect_after_participant_action(
    session_id: int, default_endpoint: str = "sessions.session_detail"
):
    next_url = request.form.get("next") or request.args.get("next")
    if next_url:
        parsed = urlparse(next_url)
        if parsed.scheme == "" and parsed.netloc == "" and next_url.startswith("/"):
            return redirect(next_url)
    return redirect(url_for(default_endpoint, session_id=session_id))


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


def _require_boolean(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError("Boolean value required")
    if isinstance(value, (int, float)):
        if value in (0, 0.0):
            return False
        if value in (1, 1.0):
            return True
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    raise ValueError("Boolean value required")


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


def attendance_edit_required(fn):
    @wraps(fn)
    def wrapper(session_id: int, *args, **kwargs):
        sess = db.session.get(Session, session_id)
        if not sess:
            abort(404)
        user_id = flask_session.get("user_id")
        if not user_id:
            if flask_session.get("participant_account_id"):
                abort(403)
            return redirect(url_for("auth.login"))
        current_user = db.session.get(User, user_id)
        if not current_user or not (
            is_admin(current_user)
            or is_kcrm(current_user)
            or is_delivery(current_user)
            or is_contractor(current_user)
        ):
            abort(403)
        if is_delivery(current_user) or is_contractor(current_user):
            if not (
                sess.lead_facilitator_id == current_user.id
                or any(f.id == current_user.id for f in sess.facilitators)
            ):
                abort(403)
        return fn(
            session_id,
            *args,
            **kwargs,
            sess=sess,
            current_user=current_user,
        )

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

    query = (
        db.session.query(Session)
        .outerjoin(Client)
        .outerjoin(WorkshopType)
        .options(
            joinedload(Session.client),
            joinedload(Session.workshop_type),
            joinedload(Session.csa_account),
            joinedload(Session.lead_facilitator),
            selectinload(Session.facilitators),
        )
    )
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
        "id": Session.id,
        "title": Session.title,
        "client": Client.name,
        "location": Session.location,
        "workshop_type": WorkshopType.name,
        "start_date": Session.start_date,
        "status": None,
        "region": Session.region,
        "material_order_status": None,
        "csa_name": None,
    }
    reverse = direction == "desc"
    special_sorts = {"status", "material_order_status", "csa_name"}
    if sort not in special_sorts:
        col = columns.get(sort) or Session.start_date
        query = query.order_by(col.desc() if reverse else col.asc())
    sessions = [s for s in query.all() if not is_material_only(s)]
    total_sessions = len(sessions)

    session_ids = [s.id for s in sessions]
    facilitator_map: dict[int, list[str]] = {}
    csa_display_map: dict[int, str] = {}
    for sess in sessions:
        names: list[str] = []
        seen_ids: set[int] = set()
        if sess.lead_facilitator and sess.lead_facilitator.id:
            seen_ids.add(sess.lead_facilitator.id)
            display = (
                (sess.lead_facilitator.full_name or "").strip()
                or (sess.lead_facilitator.email or "").strip()
            )
            if display:
                names.append(display)
        extra_facilitators = sorted(
            sess.facilitators,
            key=lambda u: (u.full_name or u.email or "").lower(),
        )
        for fac in extra_facilitators:
            if not fac or not fac.id or fac.id in seen_ids:
                continue
            seen_ids.add(fac.id)
            display = (fac.full_name or "").strip() or (fac.email or "").strip()
            if display:
                names.append(display)
        facilitator_map[sess.id] = names
        csa_display = ""
        if sess.csa_account:
            csa_display = (
                (sess.csa_account.full_name or "").strip()
                or (sess.csa_account.email or "").strip()
            )
        csa_display_map[sess.id] = csa_display

    material_status_map: dict[int, str] = {}
    if session_ids:
        shipments = (
            SessionShipping.query.with_entities(
                SessionShipping.session_id, SessionShipping.status
            )
            .filter(SessionShipping.session_id.in_(session_ids))
            .all()
        )
        for session_id_value, status_value in shipments:
            material_status_map[session_id_value] = status_value or ""

    if sort == "status":
        sessions.sort(key=lambda s: (s.computed_status or "").lower(), reverse=reverse)
    elif sort == "material_order_status":
        sessions.sort(
            key=lambda s: (material_status_map.get(s.id) or "").lower(),
            reverse=reverse,
        )
    elif sort == "csa_name":
        sessions.sort(
            key=lambda s: (csa_display_map.get(s.id) or "").lower(),
            reverse=reverse,
        )

    return render_template(
        "sessions.html",
        sessions=sessions,
        total_sessions=total_sessions,
        show_global=show_global,
        params=params,
        base_params=base_params,
        sort=sort,
        direction=direction,
        facilitator_map=facilitator_map,
        material_status_map=material_status_map,
        csa_display_map=csa_display_map,
    )


@bp.route("/new", methods=["GET", "POST"])
@staff_required
def new_session(current_user):
    if is_contractor(current_user):
        abort(403)
    workshop_types = (
        WorkshopType.query.filter(WorkshopType.active == True)
        .order_by(WorkshopType.code)
        .all()
    )
    include_all = request.args.get("include_all_facilitators") == "1"
    fac_query = User.query.filter(
        or_(User.is_kt_delivery == True, User.is_kt_contractor == True)
    )
    if not include_all:
        req_region = request.args.get("region")
        if req_region:
            fac_query = fac_query.filter(User.region == req_region)
    facilitators = (
        fac_query.order_by(
            func.lower(User.last_name).nullslast(),
            func.lower(User.first_name).nullslast(),
            func.lower(User.full_name).nullslast(),
            User.email,
        ).all()
    )
    clients = (
        Client.query.filter(Client.status == "active")
        .order_by(Client.name)
        .all()
    )
    users = User.query.order_by(User.email).all()
    cid_arg = request.args.get("client_id")
    title_arg = request.args.get("title")
    workshop_locations: list[ClientWorkshopLocation] = []
    selected_client_id = None
    if cid_arg and cid_arg.isdigit():
        candidate_id = int(cid_arg)
        candidate = db.session.get(Client, candidate_id)
        if candidate and candidate.status == "active":
            selected_client_id = candidate_id
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
        raw_sfc_link = request.form.get("sfc_link")
        sfc_link_value = (
            raw_sfc_link if raw_sfc_link and raw_sfc_link.strip() else None
        )
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
            try:
                client_lookup_id = int(cid)
            except (TypeError, ValueError):
                abort(400)
            client_record = db.session.get(Client, client_lookup_id)
            if not client_record:
                abort(400)
            if client_record.status != "active":
                return "Client is inactive.", 400
            client_record.sfc_link = sfc_link_value
            sess = Session(
                title=title,
                client_id=client_record.id,
                region=region,
                workshop_language=workshop_language,
                delivery_type="Material only",
                start_date=date.today(),
                end_date=date.today(),
                number_of_class_days=1,
                materials_only=True,
            )
            db.session.add(sess)
            db.session.flush()
            db.session.add(
                SessionShipping(session_id=sess.id, created_by=current_user.id)
            )
            enforce_material_only_rules(sess)
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
        delivery_type_normalized = (delivery_type or "").strip()
        if not delivery_type_normalized:
            missing.append("Delivery type")
        delivery_type = delivery_type_normalized or None
        workshop_language = request.form.get("workshop_language")
        if not workshop_language:
            missing.append("Workshop language")
        if workshop_language not in [c for c, _ in get_language_options()]:
            workshop_language = "en"
        capacity_str = request.form.get("capacity")
        if not capacity_str:
            missing.append("Capacity")
        days_str = request.form.get("number_of_class_days")
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
        if days_str in (None, ""):
            number_of_class_days = 1
        else:
            try:
                number_of_class_days = int(days_str)
            except ValueError:
                number_of_class_days = None
        certificate_only_selected = (
            (delivery_type or "").lower() == "certificate only"
        )
        participants_count = 0
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
        client_record = None
        if cid:
            try:
                client_lookup_id = int(cid)
            except (TypeError, ValueError):
                abort(400)
            client_record = db.session.get(Client, client_lookup_id)
            if not client_record:
                abort(400)
            if client_record.status != "active":
                return "Client is inactive.", 400
            client_record.sfc_link = sfc_link_value
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
            number_of_class_days=number_of_class_days or 1,
            materials_ordered=materials_ordered,
            ready_for_delivery=ready_for_delivery,
            info_sent=info_sent,
            delivered=delivered,
            finalized=finalized,
            no_material_order=no_material_order,
            notes=request.form.get("notes") or None,
            simulation_outline_id=so_id,
            client_id=client_record.id if client_record else None,
            workshop_location=wl,
        )
        sess.workshop_type = wt
        if number_of_class_days is None:
            flash('"# of class days" must be a whole number between 1 and 10.', "error")
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
        if number_of_class_days < 1 or number_of_class_days > 10:
            flash('"# of class days" must be between 1 and 10.', "error")
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
        if certificate_only_selected:
            ready_for_delivery = True
            materials_ordered = False
        if finalized:
            delivered = True
            ready_for_delivery = True
        if delivered:
            info_sent = True
        if ready_for_delivery and not certificate_only_selected and participants_count == 0:
            flash("Add participants before marking Ready for delivery.", "error")
            ready_for_delivery = False
        if ready_for_delivery and not certificate_only_selected:
            materials_ordered = True
        if delivered:
            materials_ordered = True
            info_sent = True
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
        enforce_material_only_rules(sess)
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
            number_of_class_days=1,
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
    workshop_types = (
        WorkshopType.query.filter(
            or_(
                WorkshopType.active == True,
                WorkshopType.id == sess.workshop_type_id,
            )
        )
        .order_by(WorkshopType.code)
        .all()
    )
    include_all = request.args.get("include_all_facilitators") == "1"
    fac_query = User.query.filter(
        or_(User.is_kt_delivery == True, User.is_kt_contractor == True)
    )
    if not include_all and sess.region:
        fac_query = fac_query.filter(User.region == sess.region)
    facilitators = (
        fac_query.order_by(
            func.lower(User.last_name).nullslast(),
            func.lower(User.first_name).nullslast(),
            func.lower(User.full_name).nullslast(),
            User.email,
        ).all()
    )
    clients = (
        Client.query.filter(Client.status == "active")
        .order_by(Client.name)
        .all()
    )
    if sess.client_id:
        current_client = db.session.get(Client, sess.client_id)
        if current_client and current_client.status != "active":
            if not any(c.id == current_client.id for c in clients):
                clients.append(current_client)
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
        original_client_id = sess.client_id
        old_ready = bool(sess.ready_for_delivery)
        ready_present = "ready_for_delivery" in request.form
        new_ready = _cb(request.form.get("ready_for_delivery"))
        if not ready_present:
            new_ready = old_ready
        raw_sfc_link = request.form.get("sfc_link")
        sfc_link_value = (
            raw_sfc_link if raw_sfc_link and raw_sfc_link.strip() else None
        )
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
        raw_delivery_type = request.form.get("delivery_type") or ""
        delivery_type_normalized = raw_delivery_type.strip()
        sess.delivery_type = delivery_type_normalized or None
        certificate_only_selected = (
            delivery_type_normalized.lower() == "certificate only"
        )
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
        days_str = request.form.get("number_of_class_days")
        if days_str in (None, ""):
            number_of_class_days = sess.number_of_class_days or 1
        else:
            try:
                number_of_class_days = int(days_str)
            except (TypeError, ValueError):
                number_of_class_days = None
        if number_of_class_days is None:
            flash('"# of class days" must be a whole number between 1 and 10.', "error")
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
        if number_of_class_days < 1 or number_of_class_days > 10:
            flash('"# of class days" must be between 1 and 10.', "error")
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
        sess.number_of_class_days = number_of_class_days
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
        if certificate_only_selected:
            new_ready = True
            materials_ordered = False
        if finalized:
            delivered = True
            new_ready = True
        if delivered:
            info_sent = True
        if new_ready and not certificate_only_selected and participants_count == 0:
            flash("Add participants before marking Ready for delivery.", "error")
            new_ready = False
        if new_ready and not certificate_only_selected:
            materials_ordered = True
        if delivered:
            materials_ordered = True
            info_sent = True
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
        has_order = False
        all_processed = True
        if materials_ordered and not old_materials and not certificate_only_selected:
            has_order, all_processed = _material_order_status(sess.id)
            if has_order and not all_processed:
                flash(MATERIALS_OUTSTANDING_MESSAGE, "error")
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
        if new_ready and not old_ready and not certificate_only_selected:
            if not has_order:
                has_order, all_processed = _material_order_status(sess.id)
            if has_order and not all_processed and not is_material_only_session(sess):
                flash(MATERIALS_OUTSTANDING_MESSAGE, "error")
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
        sess.materials_ordered = False if certificate_only_selected else materials_ordered
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
        target_client = None
        cid = request.form.get("client_id")
        if cid:
            try:
                client_lookup_id = int(cid)
            except (TypeError, ValueError):
                abort(400)
            client_record = db.session.get(Client, client_lookup_id)
            if not client_record:
                abort(400)
            if client_record.status != "active" and client_record.id != original_client_id:
                return "Client is inactive.", 400
            sess.client_id = client_record.id
            target_client = client_record
        else:
            sess.client_id = None
        if target_client is None and sess.client_id:
            target_client = db.session.get(Client, sess.client_id)
        if target_client:
            target_client.sfc_link = sfc_link_value
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
        enforce_material_only_rules(sess)
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
    attendance_days: list[int] = []
    start_dt_utc = session_start_dt_utc(sess)
    back_params = flask_session.get("sessions_list_args", {})
    badge_filename = None
    material_only = is_material_only_session(sess)
    certificate_only = is_certificate_only_session(sess)
    require_full_attendance = False
    if not material_only:
        rows = (
            db.session.query(SessionParticipant, Participant, Certificate.pdf_path)
            .options(selectinload(SessionParticipant.company_client))
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
        attendance_days = list(
            range(1, (sess.number_of_class_days or 0) + 1)
        )
        if attendance_days:
            attendance_map = defaultdict(dict)
            attendance_records = (
                db.session.query(ParticipantAttendance)
                .filter(ParticipantAttendance.session_id == session_id)
                .all()
            )
            for record in attendance_records:
                attendance_map[record.participant_id][record.day_index] = bool(
                    record.attended
                )
            for entry in participants:
                participant_id = entry["participant"].id
                entry["attendance"] = attendance_map.get(participant_id, {})
            require_full_attendance = True
        required_days = set(attendance_days)
        for entry in participants:
            attendance = entry.get("attendance", {}) if require_full_attendance else {}
            entry["has_full_attendance"] = (
                all(attendance.get(day) for day in required_days)
                if require_full_attendance
                else True
            )
        import_errors = flask_session.pop("import_errors", None)
        if csa_account:
            can_manage = csa_can_manage_participants(csa_account, sess)
        mapping, _ = get_template_mapping(sess)
        if mapping:
            badge_filename = mapping.badge_filename
    can_edit_company = bool(current_user and is_kt_staff(current_user))
    client_options: list[Client] = []
    if can_edit_company and not material_only:
        client_options = (
            Client.query.order_by(func.lower(Client.name)).all()
        )
    can_manage_attendance = bool(
        attendance_days
        and not view_csa
        and (
            current_user
            and (is_kt_staff(current_user) or is_contractor(current_user))
        )
    )
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
        attendance_days=attendance_days,
        can_manage_attendance=can_manage_attendance,
        can_edit_session=_user_can_edit_session(current_user),
        material_only_session=material_only,
        certificate_only_session=certificate_only,
        require_full_attendance=require_full_attendance,
        client_options=client_options,
        can_edit_company=can_edit_company,
    )


@bp.post("/<int:session_id>/mark-ready")
@staff_required
def mark_ready(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)

    redirect_target = (
        request.form.get("next")
        or request.args.get("next")
        or url_for("sessions.session_detail", session_id=session_id)
    )

    if sess.cancelled:
        flash("Cancelled sessions cannot be marked ready.", "error")
        return redirect(redirect_target)

    if sess.ready_for_delivery:
        flash("Session already marked ready for delivery.", "info")
        return redirect(redirect_target)

    certificate_only = is_certificate_only_session(sess)

    participants_count = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id)
        .count()
    )
    if participants_count == 0 and not certificate_only:
        flash("Add participants before marking Ready for delivery.", "error")
        return redirect(redirect_target)

    has_order, all_processed = _material_order_status(session_id)
    if (
        has_order
        and not all_processed
        and not is_material_only_session(sess)
        and not certificate_only
    ):
        flash(MATERIALS_OUTSTANDING_MESSAGE, "error")
        return redirect(redirect_target)

    now = datetime.utcnow()
    old_materials = bool(sess.materials_ordered)
    old_ready = bool(sess.ready_for_delivery)

    if not certificate_only and not sess.materials_ordered:
        sess.materials_ordered = True
        if not sess.materials_ordered_at:
            sess.materials_ordered_at = now

    if not sess.ready_for_delivery:
        sess.ready_for_delivery = True
        if not sess.ready_at:
            sess.ready_at = now

    enforce_material_only_rules(sess)

    flag_changes: list[tuple[str, bool, bool]] = []
    if not old_materials and sess.materials_ordered:
        flag_changes.append(("materials_ordered", old_materials, True))
    if not old_ready and sess.ready_for_delivery:
        flag_changes.append(("ready_for_delivery", old_ready, True))

    for flag, previous, new_value in flag_changes:
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=session_id,
                action="lifecycle_flip",
                details=f"{flag}:{previous}->{new_value}",
            )
        )

    db.session.commit()

    if not old_ready:
        summary = provision_participant_accounts_for_session(sess.id)
        total = summary["created"] + summary["reactivated"] + summary["already_active"]
        if total:
            flash(
                "Provisioned {total} (created {created}, reactivated {reactivated}; skipped staff {skipped_staff}; already active {already_active}).".format(
                    total=total, **summary
                ),
                "success",
            )
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    session_id=session_id,
                    action="provision",
                    details=
                    "created={created} skipped={skipped_staff} reactivated={reactivated} already_active={already_active}".format(
                        **summary
                    ),
                )
            )
            db.session.commit()

    flash("Session marked ready for delivery", "success")
    return redirect(redirect_target)


@bp.post("/<int:session_id>/mark-delivered")
@staff_required
def mark_delivered(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)

    redirect_target = (
        request.form.get("next")
        or request.args.get("next")
        or url_for("sessions.session_detail", session_id=session_id)
    )
    if is_material_only_session(sess):
        flash("Delivered not available for material-only sessions.", "error")
        return redirect(redirect_target)
    if sess.cancelled:
        flash("Cancelled sessions cannot be marked delivered.", "error")
        return redirect(redirect_target)
    if sess.delivered:
        flash("Session already marked delivered.", "info")
        return redirect(redirect_target)

    participants_count = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id)
        .count()
    )
    if participants_count == 0 and not (
        getattr(sess, "prework_disabled", False)
        and getattr(sess, "prework_disable_mode", None) == "silent"
    ):
        flash("Add participants before marking Delivered.", "error")
        return redirect(redirect_target)

    now = datetime.utcnow()
    flag_changes: list[tuple[str, bool, bool]] = []

    if not sess.ready_for_delivery:
        flag_changes.append(("ready_for_delivery", bool(sess.ready_for_delivery), True))
    sess.ready_for_delivery = True
    if not sess.ready_at:
        sess.ready_at = now

    flag_changes.append(("delivered", bool(sess.delivered), True))
    sess.delivered = True
    if not sess.delivered_at:
        sess.delivered_at = now

    enforce_material_only_rules(sess)

    for flag, old_value, new_value in flag_changes:
        if old_value == new_value:
            continue
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=session_id,
                action="lifecycle_flip",
                details=f"{flag}:{old_value}->{new_value}",
            )
        )

    db.session.commit()
    flash("Session marked delivered", "success")
    return redirect(redirect_target)


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
    redirect_target = (
        request.form.get("next")
        or request.args.get("next")
        or url_for("sessions.session_detail", session_id=session_id)
    )
    if not sess.delivered:
        flash("Finalized requires Delivered first.", "error")
        return redirect(redirect_target)

    has_order, all_processed = _material_order_status(session_id)
    if has_order and not all_processed and not is_material_only_session(sess):
        flash(MATERIALS_OUTSTANDING_MESSAGE, "error")
        return redirect(redirect_target)

    now = datetime.utcnow()
    material_flag_changed = False
    if not sess.materials_ordered:
        sess.materials_ordered = True
        if not sess.materials_ordered_at:
            sess.materials_ordered_at = now
        material_flag_changed = True
    if not sess.finalized:
        sess.finalized = True
        if not sess.finalized_at:
            sess.finalized_at = now
        if material_flag_changed:
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    session_id=session_id,
                    action="lifecycle_flip",
                    details="materials_ordered:False->True",
                )
            )
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=session_id,
                action="lifecycle_flip",
                details="finalized:False->True",
            )
        )
        enforce_material_only_rules(sess)
        db.session.commit()
        render_for_session(session_id)
    flash("Session finalized", "success")
    return redirect(redirect_target)


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
        return _redirect_after_participant_action(session_id)
    email = (request.form.get("email") or "").strip().lower()
    first_name = (request.form.get("first_name") or "").strip()[:100]
    last_name = (request.form.get("last_name") or "").strip()[:100]
    raw_full_name = (request.form.get("full_name") or "").strip()
    title = (request.form.get("title") or "").strip()
    raw_company_value = request.form.get("company_client_id")
    company_field_present = raw_company_value is not None
    trimmed_company = (
        (raw_company_value or "").strip() if company_field_present else ""
    )
    selected_company_id: int | None = None
    if current_user and is_kt_staff(current_user) and company_field_present:
        if trimmed_company:
            try:
                candidate = int(trimmed_company)
            except ValueError:
                candidate = None
            else:
                client = db.session.get(Client, candidate) if candidate else None
                if client:
                    selected_company_id = client.id
        else:
            selected_company_id = None
    if selected_company_id is None:
        if not company_field_present or not (current_user and is_kt_staff(current_user)):
            selected_company_id = sess.client_id
        elif trimmed_company == "":
            selected_company_id = None
        elif sess.client_id:
            selected_company_id = sess.client_id
    if not email:
        flash("Email required", "error")
        return _redirect_after_participant_action(session_id)
    user = User.query.filter(func.lower(User.email) == email).first()
    user_display = user.display_name if user else ""
    if not (first_name or last_name):
        if raw_full_name:
            split_first, split_last = split_full_name(raw_full_name)
            if split_first:
                first_name = split_first[:100]
            if split_last:
                last_name = split_last[:100]
        elif user_display:
            split_first, split_last = split_full_name(user_display)
            if split_first:
                first_name = split_first[:100]
            if split_last:
                last_name = split_last[:100]
    display_name = combine_first_last(first_name, last_name)
    full_name = (raw_full_name or display_name or user_display or email).strip()
    participant = (
        db.session.query(Participant)
        .filter(db.func.lower(Participant.email) == email)
        .one_or_none()
    )
    if not participant:
        participant = Participant(
            email=email,
            first_name=first_name or None,
            last_name=last_name or None,
            full_name=full_name or (user_display or ""),
            title=title or (user.title if user else None),
        )
        db.session.add(participant)
        db.session.flush()
    else:
        if first_name:
            participant.first_name = first_name
        if last_name:
            participant.last_name = last_name
        if full_name:
            participant.full_name = full_name
        elif user_display and not participant.full_name:
            participant.full_name = user_display
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
        link.company_client_id = selected_company_id
        db.session.add(link)
    else:
        if current_user and is_kt_staff(current_user):
            link.company_client_id = selected_company_id
        elif link.company_client_id is None and selected_company_id is not None:
            link.company_client_id = selected_company_id
    account = (
        db.session.query(ParticipantAccount)
        .filter(db.func.lower(ParticipantAccount.email) == email)
        .one_or_none()
    )
    base_name = full_name or (display_name or user_display)
    if not account:
        account = ParticipantAccount(
            email=email,
            full_name=base_name,
            certificate_name=base_name,
            is_active=True,
        )
        db.session.add(account)
        db.session.flush()
    else:
        if base_name:
            account.full_name = base_name
            if not account.certificate_name:
                account.certificate_name = base_name
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
    return _redirect_after_participant_action(session_id)


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
        return _redirect_after_participant_action(session_id)
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant_id)
        .one_or_none()
    )
    if not link:
        abort(404)
    participant = db.session.get(Participant, participant_id)
    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()[:100]
        last_name = (request.form.get("last_name") or "").strip()[:100]
        if not (first_name or last_name):
            fallback_full = (request.form.get("full_name") or participant.full_name or "").strip()
            split_first, split_last = split_full_name(fallback_full)
            if split_first:
                first_name = split_first[:100]
            if split_last:
                last_name = split_last[:100]
        combined = combine_first_last(first_name, last_name)
        full_name = (request.form.get("full_name") or combined).strip()
        title = (request.form.get("title") or "").strip()
        participant.first_name = first_name or None
        participant.last_name = last_name or None
        participant.full_name = full_name or combined or None
        participant.title = title or None
        if participant.account and (full_name or combined):
            base_name = full_name or combined
            participant.account.full_name = base_name
            if not participant.account.certificate_name:
                participant.account.certificate_name = base_name
        db.session.commit()
        flash("Participant updated", "success")
        return _redirect_after_participant_action(session_id)
    return render_template(
        "participant_edit.html",
        session_id=session_id,
        participant=participant,
        next_url=request.args.get("next"),
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
        return _redirect_after_participant_action(session_id)
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant_id)
        .one_or_none()
    )
    if link:
        db.session.delete(link)
        db.session.commit()
        flash("Participant removed", "success")
    return _redirect_after_participant_action(session_id)


@bp.get("/<int:session_id>/participants/sample-csv")
@staff_required
def sample_csv(session_id: int, current_user):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["First Name", "Last Name", "Email", "Title"])
    writer.writerow(["Jane", "Doe", "jane@example.com", "Manager"])
    writer.writerow(["John", "Smith", "john@example.com", "Director"])
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
        return _redirect_after_participant_action(session_id)
    file = request.files.get("file")
    if not file or not file.filename.endswith(".csv"):
        flash("CSV file required", "error")
        return _redirect_after_participant_action(session_id)
    text = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    header_map = {}
    for name in reader.fieldnames or []:
        key = (name or "").replace(" ", "").replace("_", "").lower()
        if key:
            header_map[key] = name
    first_header = header_map.get("firstname")
    last_header = header_map.get("lastname")
    full_header = header_map.get("fullname")
    title_header = header_map.get("title")
    email_header = header_map.get("email") or "Email"
    if not ((first_header and last_header) or full_header):
        flash(
            "CSV must include First Name and Last Name columns or a legacy Full Name column.",
            "error",
        )
        return _redirect_after_participant_action(session_id)
    imported = 0
    errors: list[str] = []
    for idx, row in enumerate(reader, start=2):
        raw_first = (
            (row.get(first_header) or "").strip() if first_header else ""
        )
        raw_last = (
            (row.get(last_header) or "").strip() if last_header else ""
        )
        raw_full = (row.get(full_header) or "").strip() if full_header else ""
        email = (row.get(email_header) or "").strip().lower()
        title = (
            (row.get(title_header) or "").strip() if title_header else ""
        )
        if not email or "@" not in email:
            errors.append(f"Row {idx}: invalid email '{email}'")
            continue
        first_name = raw_first[:100]
        last_name = raw_last[:100]
        if first_name and not last_name:
            split_first, split_last = split_full_name(first_name)
            if split_last and not raw_last:
                last_name = split_last[:100]
                first_name = (split_first or first_name)[:100]
        if last_name and not first_name:
            split_first, split_last = split_full_name(last_name)
            if split_first and not raw_first:
                first_name = split_first[:100]
                last_name = (split_last or last_name)[:100]
        if not (first_name or last_name):
            split_first, split_last = split_full_name(raw_full)
            if split_first:
                first_name = split_first[:100]
            if split_last:
                last_name = split_last[:100]
        display_name = combine_first_last(first_name, last_name)
        full_name = (raw_full or display_name).strip()
        if not full_name:
            errors.append(f"Row {idx}: name required")
            continue
        participant = (
            db.session.query(Participant)
            .filter(func.lower(Participant.email) == email)
            .one_or_none()
        )
        user = User.query.filter(func.lower(User.email) == email).first()
        user_display = user.display_name if user else ""
        if not participant:
            participant = Participant(
                email=email,
                first_name=first_name or None,
                last_name=last_name or None,
                full_name=full_name or (user_display or None),
                title=title or (user.title if user else None),
            )
            db.session.add(participant)
            db.session.flush()
        else:
            if first_name:
                participant.first_name = first_name
            if last_name:
                participant.last_name = last_name
            if full_name:
                participant.full_name = full_name
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
            link.company_client_id = sess.client_id
            db.session.add(link)
        elif link.company_client_id is None and sess.client_id:
            link.company_client_id = sess.client_id
        imported += 1
        base_name = full_name or display_name or user_display or email
        account = (
            db.session.query(ParticipantAccount)
            .filter(db.func.lower(ParticipantAccount.email) == email)
            .one_or_none()
        )
        if not account:
            account = ParticipantAccount(
                email=email,
                full_name=base_name,
                certificate_name=base_name,
                is_active=True,
            )
            db.session.add(account)
            db.session.flush()
        else:
            account.full_name = base_name
            if not account.certificate_name:
                account.certificate_name = base_name
        participant.account_id = account.id
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
    return _redirect_after_participant_action(session_id)


@bp.post("/<int:session_id>/participants/<int:participant_id>/generate")
@staff_required
def generate_single(session_id: int, participant_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    action = request.form.get("action")
    if (not sess.delivered or sess.cancelled) and action == "generate":
        flash("Delivered required before generating certificates", "error")
        return _redirect_after_participant_action(session_id)
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id, participant_id=participant_id)
        .one_or_none()
    )
    if not link:
        abort(404)
    updated = False
    if "completion_date" in request.form:
        link.completion_date = request.form.get("completion_date") or None
        updated = True
    company_raw = request.form.get("company_client_id")
    if is_kt_staff(current_user) and company_raw is not None:
        trimmed = (company_raw or "").strip()
        new_company_id: int | None = None
        if trimmed:
            try:
                new_company_id = int(trimmed)
            except ValueError:
                new_company_id = None
        if link.company_client_id != new_company_id:
            link.company_client_id = new_company_id
            updated = True
    if updated:
        db.session.commit()
    if action == "generate":
        participant = db.session.get(Participant, participant_id)
        if participant and participant.account:
            try:
                render_certificate(sess, participant.account)
            except CertificateAttendanceError as exc:
                return jsonify({"error": str(exc)}), 400
            flash("Certificate generated", "success")
        else:
            flash("No participant account", "error")
    else:
        flash("Participant updated", "success")
    return _redirect_after_participant_action(session_id)


@bp.post("/<int:session_id>/generate")
@staff_required
def generate_bulk(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    if not sess.delivered or sess.cancelled:
        flash("Delivered required before generating certificates", "error")
        return _redirect_after_participant_action(session_id)
    count, skipped, _ = render_for_session(session_id)
    if skipped:
        category = "success" if count else "warning"
        flash(
            f"Generated {count}, skipped {skipped} not Full attendance",
            category,
        )
    else:
        flash(f"Generated {count} certificates", "success")
    return _redirect_after_participant_action(session_id)


@bp.get("/<int:session_id>/certificates/export")
@staff_required
def export_certificates_zip(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)

    site_root = current_app.config.get("SITE_ROOT", "/srv")
    cert_root = os.path.join(site_root, "certificates")
    pdf_files: list[str] = []
    if os.path.isdir(cert_root):
        for year_name in sorted(os.listdir(cert_root)):
            year_dir = os.path.join(cert_root, year_name)
            if not os.path.isdir(year_dir):
                continue
            session_dir = os.path.join(year_dir, str(sess.id))
            if not os.path.isdir(session_dir):
                continue
            for filename in sorted(os.listdir(session_dir)):
                full_path = os.path.join(session_dir, filename)
                if not os.path.isfile(full_path):
                    continue
                if not filename.lower().endswith(".pdf"):
                    continue
                pdf_files.append(full_path)

    if not pdf_files:
        flash("No certificates found to export.", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in pdf_files:
            archive.write(file_path, arcname=os.path.basename(file_path))
    buffer.seek(0)
    filename = f"session-{sess.id}-certificates.zip"
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )


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
    if is_certificate_only_session(sess):
        flash("Prework is not available for certificate-only sessions.", "info")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    session_language = sess.workshop_language or "en"
    template = PreworkTemplate.query.filter_by(
        workshop_type_id=sess.workshop_type_id,
        language=session_language,
        is_active=True,
    ).first()
    participants = (
        db.session.query(Participant, ParticipantAccount)
        .join(SessionParticipant, SessionParticipant.participant_id == Participant.id)
        .outerjoin(ParticipantAccount, Participant.account_id == ParticipantAccount.id)
        .filter(SessionParticipant.session_id == sess.id)
        .order_by(
            func.lower(Participant.last_name).nullslast(),
            func.lower(Participant.first_name).nullslast(),
            func.lower(Participant.full_name).nullslast(),
            Participant.email,
        )
        .all()
    )
    if request.method == "POST":
        action = request.form.get("action")
        account_cache: dict[str, ParticipantAccount] = {}

        def _redirect_after_action() -> Response:
            next_url = request.form.get("next")
            if next_url:
                return redirect(next_url)
            return redirect(url_for("sessions.session_prework", session_id=session_id))

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

        if action == "toggle_no_prework":
            sess.no_prework = _cb(request.form.get("no_prework"))
            sess.prework_disabled = bool(sess.no_prework)
            if sess.no_prework:
                if sess.prework_disable_mode not in {"notify", "silent"}:
                    sess.prework_disable_mode = None
            else:
                sess.prework_disable_mode = None
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
            settings_row = Settings.get()
            invites_enabled = not (
                settings_row
                and settings_row.notify_account_invite_active is False
            )
            if not invites_enabled:
                current_app.logger.info(
                    "[MAIL-SKIP] account invite disabled session=%s", sess.id
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
                recipient_name = greeting_name(participant=p, account=account)
                subject = f"Workshop Portal Access: {sess.title}"
                body = render_template(
                    "email/account_invite.txt",
                    session=sess,
                    link=link,
                    account=account,
                    temp_password=temp_password,
                    greeting_name=recipient_name,
                )
                html_body = render_template(
                    "email/account_invite.html",
                    session=sess,
                    link=link,
                    account=account,
                    temp_password=temp_password,
                    greeting_name=recipient_name,
                )
                if invites_enabled:
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
            if not invites_enabled:
                flash("Account invite emails are disabled; no emails were sent.", "info")
            elif any_fail:
                flash("Some emails failed; check logs", "error")
            else:
                flash("Account links sent", "success")
            return redirect(url_for("sessions.session_prework", session_id=session_id))

        if action == "resend":
            pid = int(request.form.get("participant_id"))
            try:
                result = send_prework_invites(
                    sess,
                    [pid],
                    allow_completed_resend=True,
                    sender_id=current_user.id,
                )
            except PreworkSendError as exc:
                flash(str(exc), "error")
                return _redirect_after_action()
            if result.mail_suppressed:
                return _redirect_after_action()
            if result.any_failure:
                flash("Some emails failed; check logs", "error")
            elif result.sent_count:
                flash("Prework sent", "success")
            else:
                flash("No participants eligible for prework", "info")
            return _redirect_after_action()

        if action == "send_all":
            try:
                result = send_prework_invites(sess, sender_id=current_user.id)
            except PreworkSendError as exc:
                flash(str(exc), "error")
                return _redirect_after_action()
            if result.mail_suppressed:
                return _redirect_after_action()
            if result.any_failure:
                flash("Some emails failed; check logs", "error")
            elif result.sent_count:
                flash(
                    f"Sent prework to {result.sent_count} participant(s)",
                    "success",
                )
            else:
                flash("No participants eligible for prework", "info")
            return _redirect_after_action()

        flash("Unknown action", "error")
        return _redirect_after_action()
    rows = []
    any_assignment = False
    statuses = get_participant_prework_status(sess.id)
    assignment_ids = [
        status.assignment_id
        for status in statuses.values()
        if status and status.assignment_id
    ]
    assignment_map: dict[int, PreworkAssignment] = {}
    if assignment_ids:
        assignment_map = {
            a.id: a
            for a in PreworkAssignment.query.filter(
                PreworkAssignment.id.in_(assignment_ids)
            ).all()
        }
    for p, account in participants:
        assignment = None
        status = statuses.get(p.id)
        if status and status.assignment_id:
            assignment = assignment_map.get(status.assignment_id)
        if assignment:
            any_assignment = True
        rows.append((p, account, assignment))
    return render_template(
        "sessions/prework.html",
        session=sess,
        rows=rows,
        template=template,
        any_assignment=any_assignment,
        prework_summary=get_session_prework_summary(
            sess.id, session_language=session_language
        ),
    )


def _serialize_prework_statuses(
    statuses: dict[int, ParticipantPreworkStatus],
) -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for participant_id, status in statuses.items():
        summary = summarize_prework_status(status)
        payload[str(participant_id)] = {
            "label": summary["label"],
            "is_waived": summary["is_waived"],
            "status": summary["status"],
            "invite_count": summary["invite_count"],
            "total_sends": summary["total_sends"],
            "last_sent": summary["last_sent"].isoformat()
            if summary["last_sent"]
            else None,
            "sent_at": summary["sent_at"].isoformat()
            if summary["sent_at"]
            else None,
            "completed_at": summary["completed_at"].isoformat()
            if summary["completed_at"]
            else None,
        }
    return payload


@bp.post("/<int:session_id>/prework/send")
@staff_required
def send_prework(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)

    if is_contractor(current_user) or is_delivery(current_user):
        if not (
            sess.lead_facilitator_id == current_user.id
            or any(f.id == current_user.id for f in sess.facilitators)
        ):
            abort(403)

    if is_certificate_only_session(sess):
        message = "Prework is not available for certificate-only sessions."
        if request.is_json:
            return {"error": message}, 400
        flash(message, "error")
        return redirect(
            request.form.get("next")
            or request.args.get("next")
            or request.referrer
            or url_for("sessions.session_detail", session_id=session_id)
        )

    payload = request.get_json(silent=True) if request.is_json else None
    if payload and isinstance(payload, dict):
        raw_ids = payload.get("participant_ids")
    else:
        raw_ids = request.form.getlist("participant_ids[]") or request.form.getlist(
            "participant_ids"
        )

    participant_ids = None
    if raw_ids:
        participant_ids = []
        for value in raw_ids:
            try:
                participant_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        if not participant_ids:
            participant_ids = None

    wants_json = False
    accept = request.headers.get("Accept", "")
    if request.is_json or "application/json" in accept:
        wants_json = True

    try:
        result = send_prework_invites(
            sess, participant_ids, sender_id=current_user.id
        )
    except PreworkSendError as exc:
        if wants_json:
            return {"error": str(exc)}, 400
        flash(str(exc), "error")
        return redirect(
            request.form.get("next")
            or request.args.get("next")
            or request.referrer
            or url_for("sessions.session_prework", session_id=session_id)
        )

    statuses_payload = _serialize_prework_statuses(result.statuses)
    if result.any_failure:
        message = "Some emails failed; check logs"
        category = "error"
    elif result.sent_count:
        message = f"Sent prework to {result.sent_count} participant(s)"
        category = "success"
    else:
        message = "No participants eligible for prework"
        category = "info"

    if wants_json:
        status_code = 200 if not result.any_failure else 207
        return (
            {
                "sent_count": result.sent_count,
                "skipped_count": result.skipped_count,
                "failure_count": result.failure_count,
                "statuses": statuses_payload,
                "message": message,
                "message_category": category,
            },
            status_code,
        )

    flash(message, category)

    return redirect(
        request.form.get("next")
        or request.args.get("next")
        or request.referrer
        or url_for("sessions.session_prework", session_id=session_id)
    )


@bp.post("/<int:session_id>/attendance/toggle")
@attendance_edit_required
def toggle_attendance(session_id: int, sess: Session, current_user):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = request.form

    participant_raw = payload.get("participant_id") if payload else None
    day_raw = payload.get("day_index") if payload else None
    if participant_raw is None or day_raw is None:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "participant_id and day_index are required.",
                }
            ),
            400,
        )
    try:
        participant_id = int(participant_raw)
        day_index = int(day_raw)
    except (TypeError, ValueError):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "participant_id and day_index must be integers.",
                }
            ),
            400,
        )

    try:
        attended_value = _require_boolean(payload.get("attended") if payload else None)
    except ValueError:
        return (
            jsonify({"ok": False, "error": "attended must be true or false."}),
            400,
        )

    try:
        record = upsert_attendance(sess, participant_id, day_index, attended_value)
        db.session.commit()
    except AttendanceForbiddenError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 403
    except AttendanceValidationError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify({"ok": True, "attended": record.attended})


@bp.post("/<int:session_id>/attendance/mark_all_attended")
@attendance_edit_required
def mark_all_attendance(session_id: int, sess: Session, current_user):
    try:
        updated_count = mark_all_attended(sess)
        db.session.commit()
    except AttendanceForbiddenError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 403
    except AttendanceValidationError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify({"ok": True, "updated_count": updated_count})
