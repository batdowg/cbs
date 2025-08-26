from __future__ import annotations

import csv
import io
from functools import wraps
from datetime import date, time, datetime
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
)

from ..app import db, User
from ..models import (
    LANG_CHOICES,
    Participant,
    ParticipantAccount,
    Client,
    Session,
    SessionParticipant,
    Certificate,
    WorkshopType,
    AuditLog,
    SessionShipping,
)
from sqlalchemy import or_, func
from ..utils.certificates import generate_for_session, remove_session_certificates
from ..utils.provisioning import (
    deactivate_orphan_accounts_for_session,
    provision_participant_accounts_for_session,
)
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


def _simple_timezones():
    now = datetime.utcnow()
    seen = {}
    for name in sorted(available_timezones()):
        offset = ZoneInfo(name).utcoffset(now)
        if offset is None:
            continue
        seconds = int(offset.total_seconds())
        if seconds not in seen:
            seen[seconds] = _fmt_offset(offset)
    return [seen[k] for k in sorted(seen)]


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
    if request.method == "POST":
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
        allowed = [lbl for lbl, _ in LANG_CHOICES]
        if language not in allowed:
            language = "English"
        start_date_val = date.fromisoformat(start_date_str)
        end_date_val = date.fromisoformat(end_date_str)
        capacity_val = int(capacity_str)
        materials_ordered = _cb(request.form.get("materials_ordered"))
        ready_for_delivery = _cb(request.form.get("ready_for_delivery"))
        info_sent = _cb(request.form.get("info_sent"))
        delivered = _cb(request.form.get("delivered"))
        finalized = _cb(request.form.get("finalized"))
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
            location=request.form.get("location") or None,
            delivery_type=delivery_type,
            region=region,
            language=language,
            capacity=capacity_val,
            materials_ordered=materials_ordered,
            ready_for_delivery=ready_for_delivery,
            info_sent=info_sent,
            delivered=delivered,
            finalized=finalized,
            sponsor=request.form.get("sponsor") or None,
            notes=request.form.get("notes") or None,
            simulation_outline=request.form.get("simulation_outline") or None,
            client_id=int(cid) if cid else None,
        )
        csa_email = (request.form.get("csa_email") or "").strip().lower()
        if csa_email:
            if User.query.filter(func.lower(User.email) == csa_email).first():
                flash("That email belongs to a staff user.", "error")
            else:
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
        msg = "Session saved"
        if changes:
            msg += ": " + ", ".join(changes)
        flash(msg, "success")
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
            daily_start_time=time.fromisoformat("08:00"),
            daily_end_time=time.fromisoformat("17:00"),
            language="English",
            timezone=tz,
            capacity=16,
        ),
        workshop_types=workshop_types,
        facilitators=facilitators,
        clients=clients,
        LANG_CHOICES=LANG_CHOICES,
        include_all_facilitators=include_all,
        participants_count=0,
        today=date.today(),
        timezones=TIMEZONES,
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
    participants_count = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=sess.id)
        .count()
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
        sess.title = request.form.get("title")
        sess.start_date = request.form.get("start_date") or None
        end_date_str = request.form.get("end_date")
        sess.end_date = date.fromisoformat(end_date_str) if end_date_str else None
        sess.daily_start_time = request.form.get("daily_start_time") or None
        sess.daily_end_time = request.form.get("daily_end_time") or None
        sess.timezone = request.form.get("timezone") or None
        sess.location = request.form.get("location") or None
        sess.delivery_type = request.form.get("delivery_type") or None
        sess.region = request.form.get("region") or None
        language = request.form.get("language") or "English"
        allowed = [lbl for lbl, _ in LANG_CHOICES]
        sess.language = language if language in allowed else "English"
        sess.capacity = request.form.get("capacity") or None
        materials_ordered = _cb(request.form.get("materials_ordered")) if "materials_ordered" in request.form else old_materials
        info_sent = _cb(request.form.get("info_sent")) if "info_sent" in request.form else old_info
        delivered = _cb(request.form.get("delivered")) if "delivered" in request.form else old_delivered
        finalized = _cb(request.form.get("finalized")) if "finalized" in request.form else old_finalized
        on_hold = _cb(request.form.get("on_hold")) if "on_hold" in request.form else old_on_hold
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
        sess.sponsor = request.form.get("sponsor") or None
        sess.notes = request.form.get("notes") or None
        sess.simulation_outline = request.form.get("simulation_outline") or None
        cid = request.form.get("client_id")
        sess.client_id = int(cid) if cid else None
        csa_email = (request.form.get("csa_email") or "").strip().lower()
        if csa_email:
            if User.query.filter(func.lower(User.email) == csa_email).first():
                flash("That email belongs to a staff user.", "error")
            else:
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
        LANG_CHOICES=LANG_CHOICES,
        clients=clients,
        include_all_facilitators=include_all,
        participants_count=participants_count,
        today=date.today(),
        timezones=TIMEZONES,
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
    if User.query.filter(func.lower(User.email) == email).first():
        flash("That email belongs to a staff user.", "error")
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
    if User.query.filter(func.lower(User.email) == email).first():
        flash("That email belongs to a staff user.", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    participant = (
        db.session.query(Participant)
        .filter(db.func.lower(Participant.email) == email)
        .one_or_none()
    )
    if not participant:
        participant = Participant(email=email, full_name=full_name, title=title)
        db.session.add(participant)
        db.session.flush()
    else:
        participant.full_name = participant.full_name or full_name
        if title:
            participant.title = participant.title or title
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
    password = request.form.get("password") or ""
    confirm = request.form.get("password_confirm") or ""
    if current_user and (current_user.is_admin or current_user.is_app_admin):
        if password or confirm:
            if password != confirm:
                flash("Passwords do not match", "error")
                return redirect(url_for("sessions.session_detail", session_id=session_id))
            account = (
                db.session.query(ParticipantAccount)
                .filter(db.func.lower(ParticipantAccount.email) == email)
                .one_or_none()
            )
            if not account:
                account = ParticipantAccount(
                    email=email,
                    full_name=full_name or email,
                    certificate_name=full_name or "",
                    is_active=True,
                )
                db.session.add(account)
                db.session.flush()
            account.set_password(password)
            participant.account_id = account.id
            db.session.add(
                AuditLog(
                    user_id=current_user.id,
                    participant_id=participant.id,
                    action="password_reset_admin",
                    details=f"account_id={account.id}",
                )
            )
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
