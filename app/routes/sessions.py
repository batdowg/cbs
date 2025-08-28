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
    Language,
    ClientWorkshopLocation,
    PreworkTemplate,
    PreworkAssignment,
    PreworkEmailLog,
)
from ..utils.time import now_utc
from sqlalchemy import or_, func
from ..utils.certificates import generate_for_session, remove_session_certificates
from ..utils.provisioning import (
    deactivate_orphan_accounts_for_session,
    provision_participant_accounts_for_session,
)
from ..constants import MAGIC_LINK_TTL_DAYS
from .. import emailer
from ..utils.rbac import csa_allowed_for_session

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


def staff_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login"))
        user = db.session.get(User, user_id)
        if not user or not (user.is_app_admin or user.is_admin):
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


@bp.get("")
@staff_required
def list_sessions(current_user):
    show_global = request.args.get("global") == "1"
    query = db.session.query(Session).order_by(Session.start_date)
    if not show_global and current_user.region:
        query = query.filter(Session.region == current_user.region)
    sessions = query.all()
    return render_template("sessions.html", sessions=sessions, show_global=show_global)


@bp.route("/new", methods=["GET", "POST"])
@staff_required
def new_session(current_user):
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
    languages = (
        Language.query.filter_by(is_active=True)
        .order_by(Language.sort_order, Language.name)
        .all()
    )
    default_lang = next((l.name for l in languages if l.name == "English"), languages[0].name if languages else None)
    if request.method == "POST":
        action = request.form.get("action")
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
        language = request.form.get("language")
        if not language:
            missing.append("Language")
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
        allowed = [l.name for l in languages]
        if language not in allowed:
            language = default_lang
        start_date_val = date.fromisoformat(start_date_str)
        end_date_val = date.fromisoformat(end_date_str)
        capacity_val = int(capacity_str)
        materials_ordered = _cb(request.form.get("materials_ordered"))
        ready_for_delivery = _cb(request.form.get("ready_for_delivery"))
        info_sent = _cb(request.form.get("info_sent"))
        delivered = _cb(request.form.get("delivered"))
        finalized = _cb(request.form.get("finalized"))
        no_material_order = action == "no_material"
        if finalized:
            delivered = True
            ready_for_delivery = True
        if delivered:
            materials_ordered = True
            info_sent = True
        participants_count = 0
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
        sess = Session(
            title=title,
            start_date=start_date_val,
            end_date=end_date_val,
            daily_start_time=request.form.get("daily_start_time") or None,
            daily_end_time=request.form.get("daily_end_time") or None,
            timezone=request.form.get("timezone") or None,
            location=wl.label if wl else None,
            delivery_type=delivery_type,
            region=region,
            language=language,
            capacity=capacity_val,
            materials_ordered=materials_ordered,
            ready_for_delivery=ready_for_delivery,
            info_sent=info_sent,
            delivered=delivered,
            finalized=finalized,
            no_material_order=no_material_order,
            sponsor=request.form.get("sponsor") or None,
            notes=request.form.get("notes") or None,
            simulation_outline=request.form.get("simulation_outline") or None,
            client_id=int(cid) if cid else None,
            workshop_location=wl,
        )
        csa_email = (request.form.get("csa_email") or "").strip().lower()
        if csa_email:
            account = (
                db.session.query(ParticipantAccount)
                .filter(func.lower(ParticipantAccount.email) == csa_email)
                .one_or_none()
            )
            if not account:
                account = ParticipantAccount(
                    email=csa_email, full_name=csa_email, is_active=True
                )
                account.set_password("KTRocks!")
                db.session.add(account)
                db.session.flush()
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
        if sess.ready_for_delivery:
            summary = provision_participant_accounts_for_session(sess.id)
            total = summary["created"] + summary["reactivated"] + summary["already_active"]
            flash(
                "Provisioned {total} (created {created}, reactivated {reactivated}; kept password {kept_password}; skipped staff {skipped_staff}; already active {already_active}).".format(
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
            generate_for_session(sess.id)
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
            language=default_lang,
            timezone=tz,
            capacity=16,
            client_id=selected_client_id,
        ),
        workshop_types=workshop_types,
        facilitators=facilitators,
        clients=clients,
        languages=languages,
        include_all_facilitators=include_all,
        participants_count=0,
        today=date.today(),
        timezones=TIMEZONES,
        workshop_locations=workshop_locations,
        title_override=title_arg,
    )


@bp.route("/<int:session_id>/edit", methods=["GET", "POST"])
@staff_required
def edit_session(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
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
    participants_count = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=sess.id)
        .count()
    )
    workshop_locations = (
        ClientWorkshopLocation.query.filter_by(
            client_id=sess.client_id, is_active=True
        )
        .order_by(ClientWorkshopLocation.label)
        .all()
        if sess.client_id
        else []
    )
    languages = (
        Language.query.filter_by(is_active=True)
        .order_by(Language.sort_order, Language.name)
        .all()
    )
    extra_language = (
        sess.language
        if sess.language and sess.language not in [l.name for l in languages]
        else None
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
        old_delivered = sess.delivered
        old_materials = sess.materials_ordered
        old_info = sess.info_sent
        old_finalized = sess.finalized
        old_on_hold = sess.on_hold
        old_no_material = sess.no_material_order
        sess.title = request.form.get("title")
        sess.start_date = request.form.get("start_date") or None
        end_date_str = request.form.get("end_date")
        sess.end_date = date.fromisoformat(end_date_str) if end_date_str else None
        sess.daily_start_time = request.form.get("daily_start_time") or None
        sess.daily_end_time = request.form.get("daily_end_time") or None
        sess.timezone = request.form.get("timezone") or None
        sess.workshop_location_id = (
            int(request.form.get("workshop_location_id"))
            if request.form.get("workshop_location_id")
            else None
        )
        sess.location = (
            sess.workshop_location.label if sess.workshop_location else None
        )
        sess.delivery_type = request.form.get("delivery_type") or None
        sess.region = request.form.get("region") or None
        language = request.form.get("language") or sess.language
        allowed = [l.name for l in languages] + ([sess.language] if sess.language else [])
        sess.language = language if language in allowed else sess.language
        sess.capacity = request.form.get("capacity") or None
        materials_ordered = _cb(request.form.get("materials_ordered")) if "materials_ordered" in request.form else old_materials
        info_sent = _cb(request.form.get("info_sent")) if "info_sent" in request.form else old_info
        delivered = _cb(request.form.get("delivered")) if "delivered" in request.form else old_delivered
        finalized = _cb(request.form.get("finalized")) if "finalized" in request.form else old_finalized
        on_hold = _cb(request.form.get("on_hold")) if "on_hold" in request.form else old_on_hold
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
        sess.sponsor = request.form.get("sponsor") or None
        sess.notes = request.form.get("notes") or None
        sess.simulation_outline = request.form.get("simulation_outline") or None
        cid = request.form.get("client_id")
        sess.client_id = int(cid) if cid else None
        csa_email = (request.form.get("csa_email") or "").strip().lower()
        if csa_email:
            account = (
                db.session.query(ParticipantAccount)
                .filter(func.lower(ParticipantAccount.email) == csa_email)
                .one_or_none()
            )
            if not account:
                account = ParticipantAccount(
                    email=csa_email, full_name=csa_email, is_active=True
                )
                account.set_password("KTRocks!")
                db.session.add(account)
                db.session.flush()
            sess.csa_account_id = account.id
        else:
            sess.csa_account_id = None
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
        if new_ready and not old_ready:
            summary = provision_participant_accounts_for_session(sess.id)
            total = summary["created"] + summary["reactivated"] + summary["already_active"]
            flash(
                "Provisioned {total} (created {created}, reactivated {reactivated}; kept password {kept_password}; skipped staff {skipped_staff}; already active {already_active}).".format(
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
            generate_for_session(sess.id)
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
            changes.append(
                "Ready for delivery " + ("on" if new_ready else "off")
            )
        if info_sent != old_info:
            changes.append(
                "Workshop info sent " + ("on" if info_sent else "off")
            )
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
        return redirect(url_for("sessions.session_detail", session_id=sess.id))
    return render_template(
        "sessions/form.html",
        session=sess,
        workshop_types=workshop_types,
        facilitators=facilitators,
        languages=languages,
        extra_language=extra_language,
        clients=clients,
        include_all_facilitators=include_all,
        participants_count=participants_count,
        today=date.today(),
        timezones=TIMEZONES,
        workshop_locations=workshop_locations,
        title_override=title_arg,
    )


@bp.get("/<int:session_id>")
@csa_allowed_for_session(allow_delivered_view=True)
def session_detail(session_id: int, sess, current_user, csa_view):
    view_csa = csa_view or request.args.get("view") == "csa"
    links = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session_id)
        .join(Participant, SessionParticipant.participant_id == Participant.id)
        .all()
    )
    participants = []
    for link in links:
        participant = db.session.get(Participant, link.participant_id)
        cert = (
            db.session.query(Certificate)
            .filter_by(session_id=session_id, participant_id=link.participant_id)
            .one_or_none()
        )
        if participant:
            participants.append({"participant": participant, "link": link, "certificate": cert})
    import_errors = flask_session.pop("import_errors", None)
    return render_template(
        "session_detail.html",
        session=sess,
        participants=participants,
        import_errors=import_errors,
        csa_view=view_csa,
        current_user=current_user,
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
    if not account:
        account = ParticipantAccount(email=email, full_name=email, is_active=True)
        account.set_password("KTRocks!")
        db.session.add(account)
        db.session.flush()
    sess.csa_account_id = account.id
    db.session.commit()
    flash("CSA assigned", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/remove-csa")
@staff_required
def remove_csa(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    sess.csa_account_id = None
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
        generate_for_session(session_id)
    flash("Session finalized", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/delete")
@staff_required
def delete_session(session_id: int, current_user):
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
def add_participant(session_id: int, sess, current_user, csa_view):
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
            title=title,
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
    if not user:
        account = (
            db.session.query(ParticipantAccount)
            .filter(db.func.lower(ParticipantAccount.email) == email)
            .one_or_none()
        )
        if not account:
            account = ParticipantAccount(
                email=email,
                full_name=full_name or "",
                certificate_name=full_name or "",
                is_active=True,
            )
            account.set_password("KTRocks!")
            db.session.add(account)
            db.session.flush()
        else:
            if full_name:
                account.full_name = full_name
                if not account.certificate_name:
                    account.certificate_name = full_name
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
                "Provisioned {total} (created {created}, reactivated {reactivated}; kept password {kept_password}; skipped staff {skipped_staff}; already active {already_active}).".format(
                    total=total, **summary
                ),
                "success",
            )
    flash("Participant added", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.route("/<int:session_id>/participants/<int:participant_id>/edit", methods=["GET", "POST"])
@csa_allowed_for_session
def edit_participant(session_id: int, participant_id: int, sess, current_user, csa_view):
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
def remove_participant(session_id: int, participant_id: int, sess, current_user, csa_view):
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
def import_csv(session_id: int, sess, current_user, csa_view):
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
            details="CSA added {n} participants".format(n=imported)
            if current_user is None
            else None,
        )
    )
    db.session.commit()
    if sess.ready_for_delivery:
        summary = provision_participant_accounts_for_session(sess.id)
        total = summary["created"] + summary["reactivated"] + summary["already_active"]
        if total:
            flash(
                "Provisioned {total} (created {created}, reactivated {reactivated}; kept password {kept_password}; skipped staff {skipped_staff}; already active {already_active}).".format(
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
        generate_for_session(session_id, [participant.email])
        flash("Certificate generated", "success")
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
    count, _ = generate_for_session(session_id)
    flash(f"Generated {count} certificates", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.route("/<int:session_id>/prework", methods=["GET", "POST"])
@staff_required
def session_prework(session_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
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
        if not template:
            flash("No active prework template", "error")
            return redirect(url_for("sessions.session_prework", session_id=session_id))

        def ensure_account(participant: Participant) -> ParticipantAccount:
            account = participant.account
            if account:
                return account
            account = ParticipantAccount(
                email=(participant.email or "").lower(),
                full_name=participant.full_name or participant.email,
                is_active=True,
            )
            db.session.add(account)
            db.session.flush()
            participant.account_id = account.id
            db.session.add(participant)
            current_app.logger.info(
                f"[ACCOUNT] created participant_account_id={account.id} email={account.email}"
            )
            return account

        def prepare_assignment(account: ParticipantAccount) -> PreworkAssignment:
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

        def send_mail(assignment: PreworkAssignment, account: ParticipantAccount) -> bool:
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
                "email/prework.txt", session=sess, assignment=assignment, link=link
            )
            html_body = render_template(
                "email/prework.html", session=sess, assignment=assignment, link=link
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
                    f"[MAIL-OUT] prework session={sess.id} pa={account.id} to={account.email} subject=\"{subject}\""
                )
                return True
            current_app.logger.info(
                f"[MAIL-FAIL] prework session={sess.id} pa={account.id} to={account.email} error=\"{res.get('detail')}\""
            )
            return False

        if action == "waive":
            pid = int(request.form.get("participant_id"))
            participant = db.session.get(Participant, pid)
            account = ensure_account(participant)
            assignment = prepare_assignment(account)
            assignment.status = "WAIVED"
            assignment.sent_at = None
            assignment.magic_token_hash = None
            assignment.magic_token_expires = None
            db.session.commit()
            flash("Marked no prework", "info")
            return redirect(url_for("sessions.session_prework", session_id=session_id))

        if action == "resend":
            pid = int(request.form.get("participant_id"))
            participant = db.session.get(Participant, pid)
            account = ensure_account(participant)
            assignment = prepare_assignment(account)
            if assignment.status == "WAIVED":
                flash("Participant is waived", "error")
                return redirect(url_for("sessions.session_prework", session_id=session_id))
            send_mail(assignment, account)
            db.session.commit()
            return redirect(url_for("sessions.session_prework", session_id=session_id))

        if action == "send_all":
            any_fail = False
            for p, account in participants:
                account = ensure_account(p)
                assignment = prepare_assignment(account)
                if assignment.status == "WAIVED":
                    continue
                if not send_mail(assignment, account):
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
    for p, account in participants:
        assignment = None
        if account:
            assignment = PreworkAssignment.query.filter_by(
                session_id=sess.id, participant_account_id=account.id
            ).first()
        rows.append((p, account, assignment))
    return render_template(
        "sessions/prework.html", session=sess, rows=rows, template=template
    )
