from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, render_template, request
from sqlalchemy import func

from .sessions import staff_required
from ..app import db
from ..models import Certificate, Participant, Session, WorkshopType
from ..shared.storage import build_badge_public_url, badge_png_exists

bp = Blueprint("certificates", __name__, url_prefix="/certificates")


@bp.get("")
@staff_required
def index(current_user):
    return render_template("certificates.html")


@bp.get("/export.csv")
@staff_required
def export_csv(current_user):
    session_id = request.args.get("session_id", type=int)

    query = (
        db.session.query(Certificate, Session, Participant, WorkshopType)
        .join(Session, Session.id == Certificate.session_id)
        .join(Participant, Participant.id == Certificate.participant_id)
        .outerjoin(WorkshopType, WorkshopType.id == Session.workshop_type_id)
        .filter(Certificate.pdf_path.isnot(None))
        .filter(func.length(func.trim(Certificate.pdf_path)) > 0)
    )

    if session_id is not None:
        query = query.filter(Certificate.session_id == session_id)

    rows = (
        query.order_by(
            Session.end_date.desc().nullslast(),
            Session.id,
            Certificate.id,
        )
        .all()
    )

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

    series_cache: dict[int, str] = {}

    def _resolve_series_code(session: Session, workshop_type: WorkshopType | None) -> str:
        cached = series_cache.get(session.id)
        if cached is not None:
            return cached

        code: str | None = None
        override_series = getattr(session, "certificate_template_series", None)
        if override_series and getattr(override_series, "code", None):
            code = override_series.code
        elif workshop_type and workshop_type.cert_series:
            code = workshop_type.cert_series
        elif getattr(session, "cert_series", None):
            code = getattr(session, "cert_series")

        normalized = code.strip().upper() if code else ""
        series_cache[session.id] = normalized
        return normalized

    def _build_pdf_url(raw_path: str | None) -> str:
        trimmed = (raw_path or "").strip()
        if not trimmed:
            return ""
        lowered = trimmed.lower()
        marker = lowered.find("certificates/")
        if marker != -1:
            relative = trimmed[marker:]
            return "/" + relative.lstrip("/")
        cleaned = trimmed.lstrip("/")
        return f"/certificates/{cleaned}"

    for certificate, session, participant, workshop_type in rows:
        pdf_url = _build_pdf_url(certificate.pdf_path)
        badge_number = certificate.certification_number or ""
        badge_url = ""
        if badge_number:
            public_badge_url = build_badge_public_url(
                session.id, session.end_date, badge_number
            )
            if public_badge_url and badge_png_exists(
                session.id, session.end_date, badge_number
            ):
                badge_url = public_badge_url

        writer.writerow(
            [
                certificate.id,
                session.id,
                session.end_date.isoformat() if session.end_date else "",
                (workshop_type.code or "").upper() if workshop_type else "",
                _resolve_series_code(session, workshop_type),
                participant.display_name,
                participant.email or "",
                badge_number,
                pdf_url,
                badge_url,
            ]
        )

    resp = Response(output.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=certificates.csv"
    return resp
