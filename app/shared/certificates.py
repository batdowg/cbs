from __future__ import annotations

import os
import re
from datetime import date
from io import BytesIO
from typing import Iterable

from flask import current_app
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from ..app import db
from ..models import (
    Certificate,
    CertificateTemplate,
    CertificateTemplateSeries,
    Participant,
    ParticipantAccount,
    Session,
    SessionParticipant,
)
from .storage import ensure_dir


LETTER_NAME_INSET_MM = 25


def slug_certificate_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9 ]+", "", name or "")
    slug = re.sub(r"\s+", "-", slug.strip()).lower()
    return slug or "name"


def render_certificate(
    session: Session, participant_account: ParticipantAccount, layout_version: str = "v1"
) -> str:
    region_val = (session.region or "").strip().lower()
    na_regions = {
        "na",
        "north america",
        "us",
        "usa",
        "united states",
        "united states of america",
        "ca",
        "canada",
        "mx",
        "mexico",
    }
    effective_size = "LETTER" if region_val in na_regions else "A4"
    lang = session.workshop_language or "en"
    assets_dir = os.path.join(current_app.root_path, "assets")
    if not session.workshop_type or not session.workshop_type.cert_series:
        raise ValueError("Workshop type missing certificate series")
    series_code = session.workshop_type.cert_series
    mapping = (
        db.session.query(CertificateTemplate)
        .join(CertificateTemplateSeries)
        .filter(
            CertificateTemplateSeries.code == series_code,
            CertificateTemplate.language == lang,
            CertificateTemplate.size == effective_size,
        )
        .one_or_none()
    )
    if not mapping:
        raise ValueError(
            f"Missing certificate template mapping for series={series_code} lang={lang} size={effective_size}"
        )
    template_file = mapping.filename
    template_path = os.path.join(assets_dir, template_file)
    if not os.path.exists(template_path):
        available = sorted(
            f for f in os.listdir(assets_dir)
            if f.startswith("fncert_template_")
        )
        raise FileNotFoundError(
            f"{template_file} not found; available: {', '.join(available)}"
        )
    current_app.logger.info("Using certificate template: %s", template_path)

    participant = (
        db.session.query(Participant)
        .filter(
            (Participant.account_id == participant_account.id)
            | (db.func.lower(Participant.email) == participant_account.email.lower())
        )
        .first()
    )
    if not participant:
        raise ValueError("participant not found")
    link = (
        db.session.query(SessionParticipant)
        .filter_by(session_id=session.id, participant_id=participant.id)
        .one_or_none()
    )
    if not link:
        raise ValueError("participant not in session")
    completion = link.completion_date or session.end_date
    if not completion:
        raise ValueError("missing completion date")

    workshop = session.workshop_type.name if session.workshop_type else (session.title or "")
    display_name = (
        (participant_account.certificate_name or "").strip()
        or participant_account.full_name
        or participant_account.email
    )

    base_reader = PdfReader(template_path)
    base_page = base_reader.pages[0]
    w = float(base_page.mediabox.width)
    h = float(base_page.mediabox.height)
    mm = lambda v: v * 72.0 / 25.4
    center_x = w / 2.0

    def fit_text(text: str, font_name: str, max_pt: int, min_pt: int, max_width: float) -> int:
        pt = max_pt
        while pt > min_pt and stringWidth(text, font_name, pt) > max_width:
            pt -= 1
        return pt

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(w, h))
    base_name_width = w - mm(40)
    name_width = base_name_width
    if effective_size == "LETTER":
        name_width -= mm(2 * LETTER_NAME_INSET_MM)
    name_pt = fit_text(display_name, "Times-Italic", 48, 32, name_width)
    c.setFont("Times-Italic", name_pt)
    c.setFillGray(0.25)
    c.drawCentredString(center_x, mm(145), display_name)

    workshop_pt = fit_text(workshop, "Helvetica", 40, 28, w - mm(40))
    c.setFont("Helvetica", workshop_pt)
    c.setFillGray(0.3)
    c.drawCentredString(center_x, mm(102), workshop)

    c.setFont("Helvetica", 20)
    c.setFillGray(0.3)
    c.drawCentredString(center_x, mm(83), completion.strftime("%d %B %Y").lstrip("0"))

    c.save()
    buffer.seek(0)
    overlay_page = PdfReader(buffer).pages[0]
    base_page.merge_page(overlay_page)
    writer = PdfWriter()
    writer.add_page(base_page)

    year = completion.year
    rel_dir = os.path.join("certificates", str(year), str(session.id))
    ensure_dir(os.path.join("/srv", rel_dir))
    code = (
        session.workshop_type.code
        if session.workshop_type and session.workshop_type.code
        else "WORKSHOP"
    )
    filename = f"{code}_{slug_certificate_name(display_name)}_{completion.strftime('%Y-%m-%d')}.pdf"
    rel_path = os.path.join(rel_dir, filename)
    with open(os.path.join("/srv", rel_path), "wb") as f:
        writer.write(f)

    cert = (
        db.session.query(Certificate)
        .filter_by(session_id=session.id, participant_id=participant.id)
        .one_or_none()
    )
    if not cert:
        cert = Certificate(session_id=session.id, participant_id=participant.id)
        db.session.add(cert)
    cert.certificate_name = display_name
    cert.workshop_name = workshop
    cert.workshop_date = completion
    cert.pdf_path = rel_path
    db.session.commit()
    current_app.logger.info(
        "[CERT] email=%s session=%s path=%s",
        participant_account.email,
        session.id,
        rel_path,
    )
    return rel_path


def render_for_session(session_id: int, emails: Iterable[str] | None = None):
    session = db.session.get(Session, session_id)
    if not session or getattr(session, "cancelled", False):
        return 0, []
    q = (
        db.session.query(SessionParticipant)
        .join(Participant, SessionParticipant.participant_id == Participant.id)
        .filter(SessionParticipant.session_id == session_id)
    )
    if emails:
        emails = [e.lower() for e in emails]
        q = q.filter(db.func.lower(Participant.email).in_(emails))
    count = 0
    paths: list[str] = []
    for link in q.all():
        participant = db.session.get(Participant, link.participant_id)
        if not participant or not participant.account:
            continue
        try:
            rel_path = render_certificate(session, participant.account)
            count += 1
            paths.append(rel_path)
        except Exception:
            current_app.logger.exception(
                "[CERT-FAIL] email=%s session=%s", participant.email, session.id
            )
    return count, paths


def remove_session_certificates(session_id: int, end_date: date) -> int:
    year = (end_date or date.today()).year
    base_dir = os.path.join("/srv", "certificates", str(year), str(session_id))
    removed = 0
    if os.path.isdir(base_dir):
        for name in os.listdir(base_dir):
            if name.lower().endswith(".pdf"):
                try:
                    os.remove(os.path.join(base_dir, name))
                    removed += 1
                except FileNotFoundError:
                    pass
    return removed
