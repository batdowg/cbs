from datetime import date, datetime, time

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func, or_

from ..app import db, User
from ..models import (
    AuditLog,
    Client,
    ClientWorkshopLocation,
    Session,
    WorkshopType,
)
from ..shared.acl import is_contractor
from ..shared.languages import get_language_options
from ..shared.rbac import certificate_session_manager_required

bp = Blueprint(
    "certificate_sessions",
    __name__,
    url_prefix="/certificate-sessions",
)

REGION_OPTIONS = ["NA", "EU", "SEA", "Other"]


def _build_certificate_title(
    client: Client | None, workshop_type: WorkshopType | None
) -> str:
    parts: list[str] = []
    if client and client.name:
        parts.append(client.name)
    if workshop_type and workshop_type.code:
        parts.append(workshop_type.code)
    parts.append("Certificate Session")
    return " – ".join(parts)


def _load_locations(client_id: int | None) -> list[ClientWorkshopLocation]:
    if not client_id:
        return []
    return (
        ClientWorkshopLocation.query.filter_by(
            client_id=client_id, is_active=True
        )
        .order_by(ClientWorkshopLocation.label)
        .all()
    )


@bp.route("/new", methods=["GET", "POST"], endpoint="new", strict_slashes=False)
@certificate_session_manager_required
def new_certificate_session(current_user):
    if is_contractor(current_user):
        abort(403)

    clients = (
        Client.query.filter(Client.status == "active")
        .order_by(func.lower(Client.name))
        .all()
    )
    workshop_types = (
        WorkshopType.query.filter(WorkshopType.active == True)
        .order_by(WorkshopType.code)
        .all()
    )
    facilitators = (
        User.query.filter(or_(User.is_kt_delivery == True, User.is_kt_contractor == True))
        .order_by(
            func.lower(User.last_name).nullslast(),
            func.lower(User.first_name).nullslast(),
            func.lower(User.full_name).nullslast(),
            User.email,
        )
        .all()
    )
    facilitator_ids = {fac.id for fac in facilitators}

    form = request.form if request.method == "POST" else None
    client_id_arg = (
        request.form.get("client_id")
        if request.method == "POST"
        else request.args.get("client_id")
    )
    selected_client_id: int | None = None
    if client_id_arg and client_id_arg.isdigit():
        selected_client_id = int(client_id_arg)
    locations = _load_locations(selected_client_id)

    if request.method == "POST":
        errors: list[str] = []
        client_record: Client | None = None
        client_raw = request.form.get("client_id")
        if not client_raw:
            errors.append("Client is required.")
        else:
            try:
                client_id = int(client_raw)
            except (TypeError, ValueError):
                client_id = None
            if client_id is None:
                errors.append("Select an active client.")
            else:
                client_record = db.session.get(Client, client_id)
                if not client_record or client_record.status != "active":
                    errors.append("Select an active client.")
                else:
                    selected_client_id = client_id
                    locations = _load_locations(client_id)

        region = request.form.get("region") or ""
        if region not in REGION_OPTIONS:
            errors.append("Region is required.")

        workshop_type: WorkshopType | None = None
        wt_raw = request.form.get("workshop_type_id")
        if not wt_raw:
            errors.append("Workshop type is required.")
        else:
            try:
                wt_id = int(wt_raw)
            except (TypeError, ValueError):
                wt_id = None
            if wt_id is None:
                errors.append("Workshop type is required.")
            else:
                workshop_type = db.session.get(WorkshopType, wt_id)
                if not workshop_type or not workshop_type.active:
                    errors.append("Select an active workshop type.")

        language_options = dict(get_language_options())
        language_code = request.form.get("workshop_language") or ""
        if language_code not in language_options:
            errors.append("Language is required.")

        start_date_val: date | None = None
        start_raw = request.form.get("start_date")
        if not start_raw:
            errors.append("Start date is required.")
        else:
            try:
                start_date_val = date.fromisoformat(start_raw)
            except ValueError:
                errors.append("Start date is invalid.")

        end_date_val: date | None = None
        end_raw = request.form.get("end_date")
        if not end_raw:
            errors.append("End date is required.")
        else:
            try:
                end_date_val = date.fromisoformat(end_raw)
            except ValueError:
                errors.append("End date is invalid.")

        if start_date_val and end_date_val and end_date_val < start_date_val:
            errors.append("End date must be on or after the start date.")

        daily_start_val: time | None = None
        daily_start_raw = request.form.get("daily_start_time") or ""
        if not daily_start_raw:
            errors.append("Daily start time is required.")
        else:
            try:
                daily_start_val = time.fromisoformat(daily_start_raw)
            except ValueError:
                errors.append("Daily start time is invalid.")

        daily_end_val: time | None = None
        daily_end_raw = request.form.get("daily_end_time") or ""
        if not daily_end_raw:
            errors.append("Daily end time is required.")
        else:
            try:
                daily_end_val = time.fromisoformat(daily_end_raw)
            except ValueError:
                errors.append("Daily end time is invalid.")

        number_of_class_days: int | None = None
        days_raw = request.form.get("number_of_class_days")
        if not days_raw:
            errors.append("# of class days is required.")
        else:
            try:
                number_of_class_days = int(days_raw)
            except (TypeError, ValueError):
                number_of_class_days = None
        if number_of_class_days is not None and not (1 <= number_of_class_days <= 10):
            errors.append("# of class days must be between 1 and 10.")

        location: ClientWorkshopLocation | None = None
        location_raw = request.form.get("workshop_location_id")
        if location_raw:
            try:
                location_id = int(location_raw)
            except (TypeError, ValueError):
                location_id = None
            if location_id is None:
                errors.append("Workshop location is invalid.")
            else:
                location = db.session.get(ClientWorkshopLocation, location_id)
                if not location or (client_record and location.client_id != client_record.id):
                    errors.append("Select a location for the chosen client.")
                elif not location.is_active:
                    errors.append("Select an active workshop location.")

        lead_id: int | None = None
        lead_raw = request.form.get("lead_facilitator_id")
        if lead_raw:
            try:
                lead_id = int(lead_raw)
            except (TypeError, ValueError):
                errors.append("Lead facilitator is invalid.")
                lead_id = None
            if lead_id and lead_id not in facilitator_ids:
                errors.append("Select a valid lead facilitator.")
                lead_id = None

        additional_ids: list[int] = []
        for fid in request.form.getlist("additional_facilitators"):
            if not fid:
                continue
            try:
                parsed = int(fid)
            except (TypeError, ValueError):
                errors.append("Additional facilitator selection is invalid.")
                continue
            if lead_id and parsed == lead_id:
                continue
            if parsed not in facilitator_ids:
                errors.append("Additional facilitator selection is invalid.")
                continue
            additional_ids.append(parsed)

        if errors:
            for message in errors:
                flash(message, "error")
            return (
                render_template(
                    "certificates/new_session.html",
                    clients=clients,
                    workshop_types=workshop_types,
                    facilitators=facilitators,
                    language_options=get_language_options(),
                    regions=REGION_OPTIONS,
                    locations=locations,
                    selected_client_id=selected_client_id,
                    form=request.form,
                ),
                400,
            )

        sess = Session(
            title=_build_certificate_title(client_record, workshop_type),
            client_id=client_record.id if client_record else None,
            region=region,
            workshop_type=workshop_type,
            workshop_language=language_code,
            start_date=start_date_val,
            end_date=end_date_val,
            daily_start_time=daily_start_val,
            daily_end_time=daily_end_val,
            number_of_class_days=number_of_class_days or 1,
            delivery_type="Certificate only",
            ready_for_delivery=True,
            materials_ordered=False,
            no_material_order=True,
            no_prework=True,
            prework_disabled=True,
            workshop_location=location,
            location=location.label if location else None,
        )
        sess.is_certificate_only = True
        sess.ready_at = datetime.utcnow()

        if lead_id:
            sess.lead_facilitator_id = lead_id
        if additional_ids:
            sess.facilitators = (
                User.query.filter(User.id.in_(additional_ids)).all()
            )

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

        flash("Certificate session created and marked ready for delivery.", "success")
        return redirect(url_for("sessions.session_detail", session_id=sess.id))

    return render_template(
        "certificates/new_session.html",
        clients=clients,
        workshop_types=workshop_types,
        facilitators=facilitators,
        language_options=get_language_options(),
        regions=REGION_OPTIONS,
        locations=locations,
        selected_client_id=selected_client_id,
        form=form,
    )
