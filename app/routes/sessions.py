from __future__ import annotations

import csv
import io
from functools import wraps
from datetime import date

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
    WorkshopType,
    AuditLog,
)
from sqlalchemy import or_, func
from ..utils.certificates import generate_for_session
from ..utils.provisioning import (
    deactivate_orphan_accounts_for_session,
    provision_participant_accounts_for_session,
)
from ..utils.rbac import csa_allowed_for_session

bp = Blueprint("sessions", __name__, url_prefix="/sessions")

TRUTHY = {"1", "on", "true", "t", "y", "yes", "True", "TRUE"}
FALSY = {"0", "off", "false", "f", "n", "no", "False", "FALSE", ""}

def get_checkbox(form, name, default=None):
    if name not in form:
        return default  # missing field => leave as-is (read-only views)
    v = (form.get(name) or "").strip()
    if v in TRUTHY:
        return True
    if v in FALSY:
        return False
    return bool(v)


BASIC_STATUSES = ["New", "On Hold", "Cancelled"]
ADVANCED_STATUSES = ["Confirmed", "Delivered", "Closed", "Cancelled"]


def staff_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = flask_session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))
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
        wt_id = request.form.get("workshop_type_id")
        if not wt_id:
            flash("Workshop Type required", "error")
            return redirect(url_for("sessions.new_session"))
        wt = db.session.get(WorkshopType, int(wt_id))
        language = request.form.get("language") or "English"
        allowed = [lbl for lbl, _ in LANG_CHOICES]
        if language not in allowed:
            language = "English"
        end_date_str = request.form.get("end_date")
        end_date_val = date.fromisoformat(end_date_str) if end_date_str else None
        confirmed_ready = get_checkbox(request.form, "confirmed_ready", default=False)
        delivered = get_checkbox(request.form, "delivered", default=False)
        if delivered and end_date_val and end_date_val > date.today():
            flash(
                "Cannot mark Delivered before End Date. Adjust End Date first.",
                "error",
            )
            delivered = False
        if delivered:
            confirmed_ready = True
        status = request.form.get("status") or "New"
        if confirmed_ready:
            status = "Confirmed"
        elif status not in BASIC_STATUSES:
            flash("Status reset to New because Confirmed-Ready is off.", "error")
            status = "New"
        cid = request.form.get("client_id")
        sess = Session(
            title=request.form.get("title"),
            start_date=request.form.get("start_date") or None,
            end_date=end_date_val,
            daily_start_time=request.form.get("daily_start_time") or None,
            daily_end_time=request.form.get("daily_end_time") or None,
            timezone=request.form.get("timezone") or None,
            location=request.form.get("location") or None,
            delivery_type=request.form.get("delivery_type") or None,
            region=request.form.get("region") or None,
            language=language,
            capacity=request.form.get("capacity") or None,
            status=status,
            confirmed_ready=confirmed_ready,
            delivered=delivered,
            sponsor=request.form.get("sponsor") or None,
            notes=request.form.get("notes") or None,
            simulation_outline=request.form.get("simulation_outline") or None,
            client_id=int(cid) if cid else None,
        )
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
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=sess.id,
                action="session_create",
                details=f"session_id={sess.id}",
            )
        )
        db.session.commit()
        if sess.confirmed_ready:
            summary = provision_participant_accounts_for_session(sess.id)
            total = summary["created"] + summary["reactivated"] + summary["already_active"]
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
        if sess.delivered:
            flash("Session marked Delivered", "success")
        flash("Session saved", "success")
        return redirect(url_for("sessions.session_detail", session_id=sess.id))
    return render_template(
        "sessions/form.html",
        session=Session(),
        workshop_types=workshop_types,
        facilitators=facilitators,
        clients=clients,
        LANG_CHOICES=LANG_CHOICES,
        STATUS_CHOICES=BASIC_STATUSES,
        include_all_facilitators=include_all,
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
    if request.method == "POST":
        wt_id = request.form.get("workshop_type_id")
        if wt_id:
            sess.workshop_type = db.session.get(WorkshopType, int(wt_id))
        old_confirmed = sess.confirmed_ready
        old_delivered = sess.delivered
        old_status = sess.status or "New"
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
        new_ready = get_checkbox(request.form, "confirmed_ready", default=old_confirmed)
        delivered = get_checkbox(request.form, "delivered", default=old_delivered)
        if delivered:
            if not (new_ready or old_confirmed):
                flash("Delivered requires Confirmed-Ready.", "error")
                delivered = False
                new_ready = old_confirmed
            elif sess.end_date and sess.end_date > date.today():
                flash(
                    "This session cannot be marked as Delivered — Workshop End Date is in the future.",
                    "error",
                )
                delivered = False
                new_ready = old_confirmed
            else:
                new_ready = True
        status = request.form.get("status") or old_status
        if not new_ready:
            if status not in BASIC_STATUSES:
                flash("Status reset to New because Confirmed-Ready is off.", "error")
                status = old_status if old_status in BASIC_STATUSES else "New"
        else:
            if not old_confirmed:
                status = "Confirmed"
            elif status not in ADVANCED_STATUSES:
                flash("Status reset to Confirmed because Confirmed-Ready is on.", "error")
                status = old_status if old_status in ADVANCED_STATUSES else "Confirmed"
        sess.confirmed_ready = new_ready
        sess.status = status
        sess.delivered = delivered
        sess.sponsor = request.form.get("sponsor") or None
        sess.notes = request.form.get("notes") or None
        sess.simulation_outline = request.form.get("simulation_outline") or None
        cid = request.form.get("client_id")
        sess.client_id = int(cid) if cid else None
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
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=sess.id,
                action="session_update",
                details=f"session_id={sess.id}",
            )
        )
        db.session.commit()
        if new_ready and not old_confirmed:
            summary = provision_participant_accounts_for_session(sess.id)
            total = summary["created"] + summary["reactivated"] + summary["already_active"]
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
        if delivered and not old_delivered:
            flash("Session marked Delivered", "success")
        if sess.status in ["Cancelled", "On Hold"]:
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
        flash("Session saved", "success")
        return redirect(url_for("sessions.session_detail", session_id=sess.id))
    status_choices = ADVANCED_STATUSES if sess.confirmed_ready else BASIC_STATUSES
    return render_template(
        "sessions/form.html",
        session=sess,
        workshop_types=workshop_types,
        facilitators=facilitators,
        LANG_CHOICES=LANG_CHOICES,
        STATUS_CHOICES=status_choices,
        clients=clients,
        include_all_facilitators=include_all,
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
        if participant:
            participants.append({"participant": participant, "link": link})
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
        account = ParticipantAccount(email=email, is_active=True)
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


@bp.post("/<int:session_id>/participants/add")
@csa_allowed_for_session
def add_participant(session_id: int, sess, current_user, csa_view):
    email = (request.form.get("email") or "").strip().lower()
    full_name = (request.form.get("full_name") or "").strip()
    title = (request.form.get("title") or "").strip()
    if not email:
        flash("Email required", "error")
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
    db.session.commit()
    flash("Participant added", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.route("/<int:session_id>/participants/<int:participant_id>/edit", methods=["GET", "POST"])
@csa_allowed_for_session
def edit_participant(session_id: int, participant_id: int, sess, current_user, csa_view):
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
    db.session.commit()
    flask_session["import_errors"] = errors
    flash(f"Imported {imported}, skipped {len(errors)}", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))


@bp.post("/<int:session_id>/participants/<int:participant_id>/generate")
@staff_required
def generate_single(session_id: int, participant_id: int, current_user):
    sess = db.session.get(Session, session_id)
    if not sess:
        abort(404)
    if not sess.delivered:
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
    if not sess.delivered:
        flash("Delivered required before generating certificates", "error")
        return redirect(url_for("sessions.session_detail", session_id=session_id))
    count, _ = generate_for_session(session_id)
    flash(f"Generated {count} certificates", "success")
    return redirect(url_for("sessions.session_detail", session_id=session_id))
