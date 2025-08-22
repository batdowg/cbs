from __future__ import annotations

import os
from datetime import date
from io import BytesIO
from typing import Iterable

from flask import current_app
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from ..app import db
from ..models import (
    Certificate,
    Participant,
    Session,
    SessionParticipant,
)
from .storage import ensure_dir


def _output_paths(session: Session, participant: Participant) -> tuple[str, str]:
    year = (session.end_date or date.today()).year
    session_folder = session.code or str(session.id)
    rel_dir = os.path.join("certificates", str(year), session_folder)
    filename = f"{participant.email}.pdf"
    rel_path = os.path.join(rel_dir, filename)
    abs_path = os.path.join("/srv", rel_path)
    return rel_path, abs_path


def generate_certificate(participant: Participant, session: Session) -> str:
    rel_path, abs_path = _output_paths(session, participant)

    cert = (
        db.session.query(Certificate)
        .filter_by(session_id=session.id, participant_id=participant.id)
        .one_or_none()
    )
    workshop = (
        session.workshop_type.name
        if session.workshop_type
        else session.title
    ) or ""
    completion = session.end_date or date.today()

    template_path = os.path.join(
        current_app.root_path, "assets", "certificate_template.pdf"
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

    display_name = (
        (participant.account.certificate_name or "").strip()
        if participant.account
        else ""
    ) or participant.full_name or participant.email

    name_pt = fit_text(display_name, "Times-Italic", 48, 32, w - mm(40))
    c.setFont("Times-Italic", name_pt)
    c.setFillGray(0.25)
    c.drawCentredString(center_x, mm(145), display_name)

    workshop_pt = fit_text(workshop, "Helvetica", 40, 28, w - mm(40))
    c.setFont("Helvetica", workshop_pt)
    c.setFillGray(0.3)
    c.drawCentredString(center_x, mm(102), workshop)

    c.setFont("Helvetica", 20)
    c.setFillGray(0.3)
    c.drawCentredString(
        center_x, mm(83), completion.strftime("%d %B %Y").lstrip("0")
    )

    c.save()
    buffer.seek(0)

    overlay_page = PdfReader(buffer).pages[0]
    base_page.merge_page(overlay_page)

    writer = PdfWriter()
    writer.add_page(base_page)
    ensure_dir(os.path.dirname(abs_path))
    with open(abs_path, "wb") as f:
        writer.write(f)

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
        participant.email,
        session.code or session.id,
        rel_path,
    )
    return rel_path


def generate_for_session(session_id: int, emails: Iterable[str] | None = None):
    session = db.session.get(Session, session_id)
    if not session:
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
        if not participant:
            continue
        completion = link.completion_date or session.end_date
        if not completion:
            continue
        rel_path = generate_certificate(participant, session)
        count += 1
        paths.append(rel_path)
    return count, paths
