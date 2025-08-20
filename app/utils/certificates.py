from __future__ import annotations

import os
from datetime import date
from typing import Iterable

from flask import current_app

from ..app import db
from ..certgen import make_certificate_pdf
from ..models import Certificate, Participant, Session, SessionParticipant


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
    make_certificate_pdf(
        abs_path,
        name=participant.full_name or participant.email,
        workshop=session.title or "",
        date=session.end_date or date.today(),
    )
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
        cert = (
            db.session.query(Certificate)
            .filter_by(session_id=session.id, participant_id=participant.id)
            .one_or_none()
        )
        if not cert:
            cert = Certificate(session_id=session.id, participant_id=participant.id)
            db.session.add(cert)
        cert.certificate_name = participant.full_name
        cert.workshop_name = session.title
        cert.workshop_date = completion
        cert.pdf_path = rel_path
        count += 1
        paths.append(rel_path)
    db.session.commit()
    return count, paths
