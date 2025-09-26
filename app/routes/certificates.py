from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, render_template, request
from sqlalchemy.orm import joinedload

from .sessions import staff_required
from ..app import db
from ..models import Certificate, Participant, Session
from ..shared.storage import build_badge_public_url

bp = Blueprint("certificates", __name__)


@bp.get("/certificates")
@bp.get("/certificates/")
@staff_required
def index(current_user):
    return render_template("certificates.html")


@bp.get("/exports/certificates.csv")
@staff_required
def export_csv(current_user):
    session_id = request.args.get("session_id", type=int)
    query = (
        db.session.query(Certificate, Participant)
        .join(Participant, Certificate.participant_id == Participant.id)
        .options(joinedload(Certificate.session).joinedload(Session.workshop_type))
        .order_by(Certificate.issued_at.desc(), Certificate.id.desc())
    )
    if session_id:
        query = query.filter(Certificate.session_id == session_id)

    certificates = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "CertificateId",
            "SessionId",
            "SessionEndDate",
            "WorkshopTypeCode",
            "CertSeriesCode",
            "LearnerName",
            "LearnerEmail",
            "BadgeNumber",
            "PdfUrl",
            "BadgeUrl",
        ]
    )

    for cert, participant in certificates:
        session = getattr(cert, "session", None)
        workshop_type = getattr(session, "workshop_type", None) if session else None

        session_end = getattr(session, "end_date", None)
        session_end_value = session_end.isoformat() if session_end else ""

        workshop_type_code = ""
        if workshop_type and getattr(workshop_type, "code", None):
            workshop_type_code = workshop_type.code or ""
        elif session and getattr(session, "code", None):
            workshop_type_code = session.code or ""

        cert_series_code = (
            workshop_type.cert_series if workshop_type and workshop_type.cert_series else ""
        )

        learner_name = participant.display_name if participant else ""
        learner_email = participant.email if participant else ""

        badge_number = cert.certification_number or ""

        pdf_path = (cert.pdf_path or "").lstrip("/")
        pdf_url = f"/certificates/{pdf_path}" if pdf_path else ""

        badge_url = ""
        if badge_number and session_end:
            badge_url = build_badge_public_url(cert.session_id, session_end, badge_number) or ""

        writer.writerow(
            [
                cert.id,
                cert.session_id or "",
                session_end_value,
                workshop_type_code,
                cert_series_code,
                learner_name,
                learner_email,
                badge_number,
                pdf_url,
                badge_url or "",
            ]
        )

    resp = Response(output.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=certificates.csv"
    return resp
