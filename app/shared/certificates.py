from __future__ import annotations

import os
import re
from datetime import date, datetime
from io import BytesIO
from typing import Iterable, Sequence

from flask import current_app
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth

from ..app import db
from ..models import (
    Certificate,
    CertificateTemplate,
    CertificateTemplateSeries,
    Language,
    Participant,
    ParticipantAccount,
    Session,
    SessionParticipant,
)
from ..shared.certificates_layout import (
    DEFAULT_LANGUAGE_FONT_CODES,
    DETAIL_LABELS,
    SAFE_FALLBACK_FONT,
    sanitize_series_layout,
)
from ..shared.languages import LANG_CODE_NAMES
from .storage import ensure_dir, write_atomic


LETTER_NAME_INSET_MM = 25
DEFAULT_BOTTOM_MARGIN_MM = 20
DETAILS_FONT_SIZE_PT = 12
DETAILS_LINE_SPACING_PT = 14


def slug_certificate_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9 ]+", "", name or "")
    slug = re.sub(r"\s+", "-", slug.strip()).lower()
    return slug or "name"


def get_template_mapping(session: Session) -> tuple[CertificateTemplate | None, str]:
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
    if not session.workshop_type or not session.workshop_type.cert_series:
        return None, effective_size
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
    return mapping, effective_size


def render_certificate(
    session: Session,
    participant_account: ParticipantAccount,
    layout_version: str = "v1",
) -> str:
    assets_dir = os.path.join(current_app.root_path, "assets")
    mapping, effective_size = get_template_mapping(session)
    if not mapping:
        raise ValueError("Missing certificate template mapping for session")
    template_file = mapping.filename
    template_path = os.path.join(assets_dir, template_file)
    if not os.path.exists(template_path):
        available = sorted(
            f for f in os.listdir(assets_dir) if f.startswith("fncert_template_")
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

    workshop = (
        session.workshop_type.name if session.workshop_type else (session.title or "")
    )
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

    series_layout = sanitize_series_layout(mapping.series.layout_config)
    size_layout = series_layout.get(effective_size, series_layout["A4"])
    allowed_fonts = _language_allowed_fonts(session.workshop_language)
    available_fonts = _available_font_codes()

    name_font = _resolve_font(
        size_layout["name"]["font"],
        allowed_fonts,
        available_fonts,
        session,
        effective_size,
        "name",
    )
    workshop_font = _resolve_font(
        size_layout["workshop"]["font"],
        allowed_fonts,
        available_fonts,
        session,
        effective_size,
        "workshop",
    )
    date_font = _resolve_font(
        size_layout["date"]["font"],
        allowed_fonts,
        available_fonts,
        session,
        effective_size,
        "date",
    )
    name_y = mm(size_layout["name"]["y_mm"])
    workshop_y = mm(size_layout["workshop"]["y_mm"])
    date_y = mm(size_layout["date"]["y_mm"])

    def fit_text(
        text: str, font_name: str, max_pt: int, min_pt: int, max_width: float
    ) -> int:
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
    name_pt = fit_text(display_name, name_font, 48, 32, name_width)
    c.setFont(name_font, name_pt)
    c.setFillGray(0.25)
    c.drawCentredString(center_x, name_y, display_name)

    workshop_pt = fit_text(workshop, workshop_font, 40, 28, w - mm(40))
    c.setFont(workshop_font, workshop_pt)
    c.setFillGray(0.3)
    c.drawCentredString(center_x, workshop_y, workshop)

    c.setFont(date_font, 20)
    c.setFillGray(0.3)
    c.drawCentredString(
        center_x,
        date_y,
        completion.strftime("%d %B %Y").lstrip("0"),
    )

    details_cfg = size_layout.get("details", {})
    if details_cfg.get("enabled"):
        detail_lines = _build_details_lines(session, details_cfg.get("variables", []))
        if detail_lines:
            detail_font = _resolve_font(
                date_font,
                allowed_fonts,
                available_fonts,
                session,
                effective_size,
                "details",
            )
            margin_x = mm(DEFAULT_BOTTOM_MARGIN_MM)
            c.setFont(detail_font, DETAILS_FONT_SIZE_PT)
            c.setFillGray(0.3)
            for index, line in enumerate(detail_lines):
                y_pos = mm(DEFAULT_BOTTOM_MARGIN_MM) + index * DETAILS_LINE_SPACING_PT
                if details_cfg.get("side", "LEFT") == "RIGHT":
                    c.drawRightString(w - margin_x, y_pos, line)
                else:
                    c.drawString(margin_x, y_pos, line)

    c.save()
    buffer.seek(0)
    overlay_page = PdfReader(buffer).pages[0]
    base_page.merge_page(overlay_page)
    writer = PdfWriter()
    writer.add_page(base_page)

    year = (session.start_date or date.today()).year
    site_root = current_app.config.get("SITE_ROOT", "/srv")
    cert_root = os.path.join(site_root, "certificates")
    rel_dir = os.path.join(str(year), str(session.id))
    ensure_dir(os.path.join(cert_root, rel_dir))
    code = (
        session.workshop_type.code
        if session.workshop_type and session.workshop_type.code
        else "WORKSHOP"
    )
    filename = f"{code}_{slug_certificate_name(display_name)}_{completion.strftime('%Y-%m-%d')}.pdf"
    rel_path = os.path.join(rel_dir, filename)
    full_path = os.path.join(cert_root, rel_path)
    out_buf = BytesIO()
    writer.write(out_buf)
    write_atomic(full_path, out_buf.getvalue())
    os.chmod(full_path, 0o644)  # world-readable for Caddy

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
    site_root = current_app.config.get("SITE_ROOT", "/srv")
    base_dir = os.path.join(site_root, "certificates", str(year), str(session_id))
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


def _available_font_codes() -> set[str]:
    fonts = set(pdfmetrics.getRegisteredFontNames())
    try:
        fonts.update(pdfmetrics.standardFonts)
    except AttributeError:
        fonts.update({"Helvetica", "Times-Roman", "Courier"})
    return fonts


def _language_allowed_fonts(lang_code: str | None) -> list[str]:
    if not lang_code:
        return DEFAULT_LANGUAGE_FONT_CODES.copy()
    lang_name = LANG_CODE_NAMES.get(lang_code, lang_code)
    lang = (
        db.session.query(Language)
        .filter(db.func.lower(Language.name) == lang_name.lower())
        .one_or_none()
    )
    fonts: Sequence[str] | None = getattr(lang, "allowed_fonts", None)
    filtered = [f for f in (fonts or []) if isinstance(f, str)]
    if filtered:
        return filtered
    return DEFAULT_LANGUAGE_FONT_CODES.copy()


def _resolve_font(
    preferred: str,
    allowed_fonts: Sequence[str],
    available_fonts: set[str],
    session: Session,
    size: str,
    line: str,
) -> str:
    sanitized_allowed = [f for f in allowed_fonts if f in available_fonts]
    if preferred in sanitized_allowed:
        return preferred
    reason: str | None = None
    if preferred and preferred not in allowed_fonts:
        reason = "not allowed"
    elif preferred and preferred not in available_fonts:
        reason = "not available"
    if sanitized_allowed:
        candidate = sanitized_allowed[0]
    else:
        fallback_candidates = [f for f in (SAFE_FALLBACK_FONT,) if f in available_fonts]
        if not fallback_candidates:
            fallback_candidates = sorted(available_fonts) or [SAFE_FALLBACK_FONT]
        candidate = fallback_candidates[0]
        if not reason:
            reason = "no allowed fonts"
    current_app.logger.warning(
        "[CERT-FONT] session=%s lang=%s size=%s line=%s %s→%s (%s)",
        session.id,
        session.workshop_language,
        size,
        line,
        preferred or "<default>",
        candidate,
        reason or "fallback",
    )
    return candidate


def _build_details_lines(session: Session, variables: Sequence[str]) -> list[str]:
    lines: list[str] = []
    for key in variables:
        label = DETAIL_LABELS.get(key)
        if not label:
            continue
        value = _detail_value(session, key)
        if value:
            lines.append(f"{label}: {value}")
    return lines


def _detail_value(session: Session, key: str) -> str | None:
    if key == "contact_hours":
        return _format_contact_hours(session)
    if key == "facilitators":
        return _format_facilitators(session)
    if key == "dates":
        return _format_session_dates(session)
    if key == "location_title":
        if session.workshop_location and session.workshop_location.label:
            return session.workshop_location.label
        if session.location:
            return session.location
        return None
    if key == "class_days":
        days = session.number_of_class_days or 0
        return str(days) if days else None
    return None


def _format_contact_hours(session: Session) -> str | None:
    start = session.daily_start_time
    end = session.daily_end_time
    if not start or not end:
        return None
    start_dt = datetime.combine(date.today(), start)
    end_dt = datetime.combine(date.today(), end)
    if end_dt <= start_dt:
        return None
    hours = (end_dt - start_dt).total_seconds() / 3600
    days = session.number_of_class_days or 1
    total = hours * days
    if total <= 0:
        return None
    if abs(total - round(total)) < 0.01:
        return str(int(round(total)))
    return f"{total:.1f}".rstrip("0").rstrip(".")


def _format_facilitators(session: Session) -> str | None:
    names: list[str] = []
    if session.lead_facilitator:
        lead_name = (
            session.lead_facilitator.full_name
            or session.lead_facilitator.email
            or ""
        )
        if lead_name:
            names.append(lead_name)
    seen_ids = {getattr(session.lead_facilitator, "id", None)}
    for facilitator in session.facilitators:
        if facilitator.id in seen_ids:
            continue
        seen_ids.add(facilitator.id)
        display = facilitator.full_name or facilitator.email or ""
        if display:
            names.append(display)
    return ", ".join(names) if names else None


def _format_session_dates(session: Session) -> str | None:
    start = session.start_date
    end = session.end_date or start
    if not start and not end:
        return None
    if not start:
        start = end
    if not end:
        end = start
    start_day = start.strftime("%d").lstrip("0") or start.strftime("%d")
    end_day = end.strftime("%d").lstrip("0") or end.strftime("%d")
    start_month = start.strftime("%B")
    end_month = end.strftime("%B")
    start_year = start.strftime("%Y")
    end_year = end.strftime("%Y")
    if start == end:
        return f"{start_day} {start_month} {start_year}"
    if start_year == end_year:
        if start.month == end.month:
            return f"{start_day}–{end_day} {start_month} {start_year}"
        return f"{start_day} {start_month} – {end_day} {end_month} {start_year}"
    return f"{start_day} {start_month} {start_year} – {end_day} {end_month} {end_year}"
