from __future__ import annotations

from collections import defaultdict
from functools import wraps
import hashlib
import secrets
from datetime import timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
)
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload

from ..app import db, User
from ..models import (
    Client,
    Participant,
    ParticipantAccount,
    Session,
    SessionParticipant,
    Certificate,
    Resource,
    PreworkAssignment,
    resource_workshop_types,
)
from ..shared.acl import is_delivery, is_contractor, is_kt_staff
from ..shared.prework_summary import get_session_prework_summary
from ..shared.prework_status import (
    get_participant_prework_status,
    summarize_prework_status,
)
from ..shared.names import split_full_name, greeting_name
from ..shared.sessions_lifecycle import (
    is_certificate_only_session,
    is_material_only_session,
)
from ..shared.certificates import get_template_mapping
from ..shared.accounts import ensure_participant_account
from ..shared.constants import MAGIC_LINK_TTL_DAYS, DEFAULT_PARTICIPANT_PASSWORD
from ..shared.time import now_utc
from .. import emailer

bp = Blueprint("workshops", __name__, url_prefix="/workshops")


def facilitator_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login"))
        user = db.session.get(User, user_id)
        if not user or not (
            is_kt_staff(user) or is_delivery(user) or is_contractor(user)
        ):
            flash("Workshop view is available to assigned facilitators only.", "error")
            abort(403)
        return fn(*args, **kwargs, current_user=user)

    return wrapper


def _ensure_user_for_participant(participant: Participant) -> tuple[User | None, bool]:
    email = (participant.email or "").strip().lower()
    if not email:
        return None, False
    existing = User.query.filter(func.lower(User.email) == email).first()
    if existing:
        updated = False
        if participant.display_name and not existing.full_name:
            existing.full_name = participant.display_name
            updated = True
        if participant.first_name and not existing.first_name:
            existing.first_name = participant.first_name
            updated = True
        if participant.last_name and not existing.last_name:
            existing.last_name = participant.last_name
            updated = True
        if participant.title and not existing.title:
            existing.title = participant.title
            updated = True
        if updated:
            db.session.add(existing)
        return existing, False
    display_name = participant.display_name or email
    first_name = participant.first_name
    last_name = participant.last_name
    if not (first_name or last_name):
        split_first, split_last = split_full_name(display_name)
        first_name = first_name or split_first
        last_name = last_name or split_last
    user = User(
        email=email,
        full_name=display_name,
        first_name=first_name,
        last_name=last_name,
        title=participant.title,
        preferred_view="LEARNER",
    )
    user.set_password(DEFAULT_PARTICIPANT_PASSWORD)
    db.session.add(user)
    return user, True


@bp.get("/<int:session_id>")
@facilitator_required
def workshop_view(session_id: int, current_user):
    session = (
        db.session.query(Session)
        .options(
            joinedload(Session.client).joinedload(Client.crm),
            joinedload(Session.lead_facilitator),
            selectinload(Session.facilitators),
            joinedload(Session.workshop_type),
            joinedload(Session.simulation_outline),
            joinedload(Session.workshop_location),
            joinedload(Session.shipping_location),
            selectinload(Session.attendance_records),
        )
        .filter(Session.id == session_id)
        .one_or_none()
    )
    if not session:
        abort(404)

    material_only = is_material_only_session(session)
    certificate_only = is_certificate_only_session(session)

    is_assigned = False
    if session.lead_facilitator_id and session.lead_facilitator_id == current_user.id:
        is_assigned = True
    elif session.facilitators:
        is_assigned = any(f.id == current_user.id for f in session.facilitators)
    is_staff_viewer = is_kt_staff(current_user)

    if not is_assigned and not is_staff_viewer:
        flash("Workshop view is available to assigned facilitators only.", "error")
        abort(403)

    if material_only:
        flash("Material only sessions use the session detail view.", "info")
        return redirect(url_for("sessions.session_detail", session_id=session.id))

    facilitator_resources: list[Resource] = []
    if session.workshop_type_id:
        facilitator_resources = (
            Resource.query.filter(Resource.active == True)
            .join(resource_workshop_types)
            .filter(resource_workshop_types.c.workshop_type_id == session.workshop_type_id)
            .filter(Resource.language == (session.workshop_language or "en"))
            .filter(Resource.audience.in_(["Facilitator", "Both"]))
            .order_by(Resource.name)
            .all()
        )

    participants: list[dict[str, object]] = []
    badge_filename = None
    import_errors = None
    attendance_days: list[int] = []
    attendance_map: dict[int, dict[int, bool]] = {}
    require_full_attendance = False
    if not material_only:
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
        statuses = get_participant_prework_status(session.id)
        participants = []
        for link, participant, pdf_path in rows:
            status = statuses.get(participant.id)
            participants.append(
                {
                    "participant": participant,
                    "link": link,
                    "pdf_path": pdf_path,
                    "prework_status": status,
                    "prework_summary": summarize_prework_status(status),
                }
            )
        attendance_days = list(
            range(1, (session.number_of_class_days or 0) + 1)
        )
        if attendance_days:
            attendance_map = defaultdict(dict)
            for record in session.attendance_records:
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
        mapping, _ = get_template_mapping(session)
        if mapping:
            badge_filename = mapping.badge_filename

    can_manage_prework = bool(
        not certificate_only
        and (
            is_kt_staff(current_user)
            or is_delivery(current_user)
            or is_contractor(current_user)
        )
    )
    can_send_prework = bool(can_manage_prework and not session.prework_disabled)
    show_disable_prework = bool(can_manage_prework and not session.prework_disabled)

    can_manage_attendance = bool(
        attendance_days
        and (
            is_kt_staff(current_user)
            or is_delivery(current_user)
            or is_contractor(current_user)
        )
    )

    return render_template(
        "sessions/workshop_view.html",
        session=session,
        participants=participants,
        badge_filename=badge_filename,
        import_errors=import_errors,
        facilitator_resources=facilitator_resources,
        prework_summary=get_session_prework_summary(
            session.id, session_language=session.workshop_language
        ),
        can_send_prework=can_send_prework,
        show_disable_prework=show_disable_prework,
        require_full_attendance=require_full_attendance,
        current_user=current_user,
        attendance_days=attendance_days,
        can_manage_attendance=can_manage_attendance,
        certificate_only_session=certificate_only,
    )


@bp.post("/<int:session_id>/prework/disable")
@facilitator_required
def disable_prework(session_id: int, current_user):
    mode = (request.form.get("mode") or "").strip().lower()
    if mode not in {"notify", "silent"}:
        abort(400)

    session = db.session.get(Session, session_id)
    if not session:
        abort(404)
    if is_certificate_only_session(session):
        flash("Prework is not available for certificate-only sessions.", "error")
        return redirect(url_for("workshops.workshop_view", session_id=session.id))

    is_assigned = False
    if session.lead_facilitator_id and session.lead_facilitator_id == current_user.id:
        is_assigned = True
    elif session.facilitators:
        is_assigned = any(f.id == current_user.id for f in session.facilitators)

    if not is_assigned and not is_kt_staff(current_user):
        flash("Workshop view is available to assigned facilitators only.", "error")
        abort(403)

    session.prework_disabled = True
    session.prework_disable_mode = mode
    session.no_prework = True

    assignments = PreworkAssignment.query.filter_by(session_id=session.id).all()
    for assignment in assignments:
        assignment.status = "WAIVED"
        assignment.sent_at = None
        assignment.magic_token_hash = None
        assignment.magic_token_expires = None

    participants = (
        db.session.query(Participant)
        .join(SessionParticipant, SessionParticipant.participant_id == Participant.id)
        .filter(SessionParticipant.session_id == session.id)
        .order_by(
            func.lower(Participant.last_name).nullslast(),
            func.lower(Participant.first_name).nullslast(),
            func.lower(Participant.full_name).nullslast(),
            Participant.email,
        )
        .all()
    )

    account_cache: dict[str, ParticipantAccount] = {}
    sent_count = 0
    created_users = 0
    any_fail = False

    for participant in participants:
        email = (participant.email or "").strip().lower()
        if not email:
            continue
        try:
            account, temp_password = ensure_participant_account(
                participant, account_cache
            )
        except ValueError:
            continue
        _, created = _ensure_user_for_participant(participant)
        if created:
            created_users += 1
        if mode == "notify":
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
            recipient_name = greeting_name(participant=participant, account=account)
            subject = f"Workshop Portal Access: {session.title}"
            body = render_template(
                "email/account_invite.txt",
                session=session,
                link=link,
                account=account,
                temp_password=temp_password,
                greeting_name=recipient_name,
            )
            html_body = render_template(
                "email/account_invite.html",
                session=session,
                link=link,
                account=account,
                temp_password=temp_password,
                greeting_name=recipient_name,
            )
            try:
                res = emailer.send(account.email, subject, body, html=html_body)
            except Exception as exc:  # pragma: no cover - defensive
                res = {"ok": False, "detail": str(exc)}
            if res.get("ok"):
                sent_count += 1
                current_app.logger.info(
                    f"[MAIL-OUT] account-invite session={session.id} pa={account.id} to={account.email}"
                )
            else:
                any_fail = True
                current_app.logger.info(
                    f"[MAIL-FAIL] account-invite session={session.id} pa={account.id} to={account.email} error=\"{res.get('detail')}\""
                )

    db.session.commit()

    base_note = ""
    if created_users:
        base_note = f" Created {created_users} new user account(s)."

    if mode == "notify":
        if any_fail:
            flash(
                "Prework disabled, but some account emails failed. Check logs." + base_note,
                "error",
            )
        else:
            flash(
                f"Prework disabled. Sent {sent_count} account email(s)." + base_note,
                "success",
            )
    else:
        flash(
            "Prework disabled without sending account emails." + base_note,
            "success",
        )

    current_app.logger.info(
        f"[WORKSHOP] prework_disabled mode={mode} session={session.id} participants={len(participants)} created_users={created_users}"
    )

    return redirect(url_for("workshops.workshop_view", session_id=session.id))
