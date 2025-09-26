from __future__ import annotations

import csv
import io
from datetime import datetime

from flask import Blueprint, Response, render_template
from sqlalchemy.orm import selectinload

from .sessions import staff_required
from ..app import db
from ..models import Certificate, Participant, SessionParticipant

bp = Blueprint("certificates", __name__, url_prefix="/certificates")


@bp.get("")
@staff_required
def index(current_user):
    return render_template("certificates.html")


@bp.get("/export.csv")
@staff_required
def export_csv(current_user):
    rows = (
        db.session.query(
            Certificate,
            Participant,
            SessionParticipant.completion_date,
        )
        .join(Participant, Certificate.participant_id == Participant.id)
        .outerjoin(
            SessionParticipant,
            (SessionParticipant.session_id == Certificate.session_id)
            & (SessionParticipant.participant_id == Certificate.participant_id),
        )
        .options(selectinload(Certificate.session))
        .order_by(Certificate.issued_at.desc(), Certificate.id.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "CertificateID",
            "BadgeNumber",
            "ParticipantEmail",
            "ParticipantName",
            "CertificateName",
            "WorkshopName",
            "WorkshopDate",
            "SessionID",
            "CompletionDate",
            "IssuedAt",
            "PdfPath",
        ]
    )

    def _format_date(value: datetime | None) -> str:
        if not value:
            return ""
        if isinstance(value, datetime):
            return value.replace(microsecond=0).isoformat(sep=" ")
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    for cert, participant, completion_date in rows:
        session = cert.session
        workshop_date = (
            cert.workshop_date.isoformat() if cert.workshop_date else ""
        )
        completion_val = (
            completion_date.isoformat() if completion_date else ""
        )
        writer.writerow(
            [
                cert.id,
                cert.certification_number or "",
                participant.email,
                participant.display_name,
                cert.certificate_name,
                cert.workshop_name,
                workshop_date,
                session.id if session else cert.session_id,
                completion_val,
                _format_date(cert.issued_at),
                cert.pdf_path,
            ]
        )

    resp = Response(output.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=certificates.csv"
    return resp
