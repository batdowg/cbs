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
    DETAIL_SIZE_MAX_PERCENT,
    DETAIL_SIZE_MIN_PERCENT,
    SAFE_FALLBACK_FONT,
    sanitize_series_layout,
)
from ..shared.languages import LANG_CODE_NAMES
from .storage import ensure_dir, write_atomic


LETTER_NAME_INSET_MM = 25
DEFAULT_BOTTOM_MARGIN_MM = 20
DETAILS_FONT_SIZE_PT = 12
DETAILS_LINE_SPACING_PT = 14

DETAIL_RENDER_SEQUENCE: tuple[str, ...] = (
    "facilitators",
    "location_title",
    "dates",
    "class_days",
    "contact_hours",
)

US_COUNTRY_CODES = {
    "US",
    "USA",
    "UNITEDSTATES",
    "UNITEDSTATESOFAMERICA",
    "PUERTORICO",
    "GUAM",
    "AMERICANSAMOA",
    "NORTHERNMARIANAISLANDS",
    "COMMONWEALTHOFTHENORTHERNMARIANAISLANDS",
    "CNMI",
    "VIRGINISLANDS",
    "UNITEDSTATESVIRGINISLANDS",
    "USVIRGINISLANDS",
}

US_STATE_NAMES = {
    "AL": "ALABAMA",
    "AK": "ALASKA",
    "AZ": "ARIZONA",
    "AR": "ARKANSAS",
    "CA": "CALIFORNIA",
    "CO": "COLORADO",
    "CT": "CONNECTICUT",
    "DE": "DELAWARE",
    "FL": "FLORIDA",
    "GA": "GEORGIA",
    "HI": "HAWAII",
    "ID": "IDAHO",
    "IL": "ILLINOIS",
    "IN": "INDIANA",
    "IA": "IOWA",
    "KS": "KANSAS",
    "KY": "KENTUCKY",
    "LA": "LOUISIANA",
    "ME": "MAINE",
    "MD": "MARYLAND",
    "MA": "MASSACHUSETTS",
    "MI": "MICHIGAN",
    "MN": "MINNESOTA",
    "MS": "MISSISSIPPI",
    "MO": "MISSOURI",
    "MT": "MONTANA",
    "NE": "NEBRASKA",
    "NV": "NEVADA",
    "NH": "NEW HAMPSHIRE",
    "NJ": "NEW JERSEY",
    "NM": "NEW MEXICO",
    "NY": "NEW YORK",
    "NC": "NORTH CAROLINA",
    "ND": "NORTH DAKOTA",
    "OH": "OHIO",
    "OK": "OKLAHOMA",
    "OR": "OREGON",
    "PA": "PENNSYLVANIA",
    "RI": "RHODE ISLAND",
    "SC": "SOUTH CAROLINA",
    "SD": "SOUTH DAKOTA",
    "TN": "TENNESSEE",
    "TX": "TEXAS",
    "UT": "UTAH",
    "VT": "VERMONT",
    "VA": "VIRGINIA",
    "WA": "WASHINGTON",
    "WV": "WEST VIRGINIA",
    "WI": "WISCONSIN",
    "WY": "WYOMING",
    "DC": "DISTRICT OF COLUMBIA",
    "PR": "PUERTO RICO",
    "GU": "GUAM",
    "VI": "VIRGIN ISLANDS",
    "MP": "NORTHERN MARIANA ISLANDS",
    "AS": "AMERICAN SAMOA",
}

US_STATE_CODES = set(US_STATE_NAMES.keys())
STATE_NAME_TO_CODE = {name: code for code, name in US_STATE_NAMES.items()}
STATE_COMPACT_TO_CODE = {
    re.sub(r"[^A-Z]", "", name): code for code, name in US_STATE_NAMES.items()
}
STATE_ALIAS_TO_CODE = {
    "WASHINGTONDC": "DC",
    "USVIRGINISLANDS": "VI",
    "UNITEDSTATESVIRGINISLANDS": "VI",
    "VIRGINISLANDSUS": "VI",
    "VIRGINISLANDS": "VI",
    "NORTHERNMARIANAS": "MP",
    "COMMONWEALTHOFTHENORTHERNMARIANAISLANDS": "MP",
    "CNMI": "MP",
}


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
            size_percent_raw = details_cfg.get("size_percent", DETAIL_SIZE_MAX_PERCENT)
            try:
                size_percent_int = int(size_percent_raw)
            except (TypeError, ValueError):
                size_percent_int = DETAIL_SIZE_MAX_PERCENT
            if size_percent_int < DETAIL_SIZE_MIN_PERCENT or size_percent_int > DETAIL_SIZE_MAX_PERCENT:
                size_percent_int = max(
                    DETAIL_SIZE_MIN_PERCENT,
                    min(size_percent_int, DETAIL_SIZE_MAX_PERCENT),
                )
            scale = size_percent_int / 100.0
            detail_font_size = DETAILS_FONT_SIZE_PT * scale
            line_spacing = DETAILS_LINE_SPACING_PT * scale
            c.setFont(detail_font, detail_font_size)
            c.setFillGray(0.3)
            for index, line in enumerate(detail_lines):
                y_pos = mm(DEFAULT_BOTTOM_MARGIN_MM) + index * line_spacing
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
    warnings: list[str] | None = None,
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
    context_reason = reason or "fallback"
    current_app.logger.warning(
        "[CERT-FONT] session=%s lang=%s size=%s line=%s %s→%s (%s)",
        session.id,
        session.workshop_language,
        size,
        line,
        preferred or "<default>",
        candidate,
        context_reason,
    )
    if warnings is not None:
        warnings.append(
            (
                f"{line.title()} font {preferred or '<default>'} replaced with {candidate}"
                f" ({context_reason})."
            )
        )
    return candidate


def _build_details_lines(session: Session, variables: Sequence[str]) -> list[str]:
    selected = {var for var in variables if var in DETAIL_RENDER_SEQUENCE}
    if not selected:
        return []
    lines: list[str] = []
    if "facilitators" in selected:
        facilitators = _format_facilitators(session)
        if facilitators:
            lines.append(f"{DETAIL_LABELS['facilitators']}: {facilitators}")
    if "location_title" in selected:
        location = _format_location(session)
        if location:
            lines.append(location)
    if "dates" in selected:
        dates = _format_session_dates(session)
        if dates:
            lines.append(dates)
    class_days = _format_class_days(session) if "class_days" in selected else None
    contact_hours = (
        _format_contact_hours(session) if "contact_hours" in selected else None
    )
    if class_days and contact_hours:
        lines.append(
            f"{DETAIL_LABELS['class_days']}: {class_days} • {DETAIL_LABELS['contact_hours']}: {contact_hours}"
        )
    else:
        if class_days:
            lines.append(f"{DETAIL_LABELS['class_days']}: {class_days}")
        if contact_hours:
            lines.append(f"{DETAIL_LABELS['contact_hours']}: {contact_hours}")
    return lines


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
    start_str = _format_single_date(start)
    if start == end:
        return start_str
    end_str = _format_single_date(end)
    return f"{start_str} – {end_str}"


def _format_single_date(value: date) -> str:
    day = value.strftime("%d").lstrip("0") or value.strftime("%d")
    month = value.strftime("%B")
    year = value.strftime("%Y")
    return f"{day} {month} {year}"


def _format_class_days(session: Session) -> str | None:
    days = session.number_of_class_days or 0
    return str(days) if days else None


def _format_location(session: Session) -> str | None:
    location = session.workshop_location
    fallback: str | None = None
    if location and location.label:
        fallback = location.label
    elif session.location:
        fallback = session.location
    if not location:
        return fallback
    city = (location.city or "").strip()
    state_value = (location.state or "").strip()
    country_value = (location.country or "").strip()
    state_code = _state_abbreviation(state_value)
    is_us = _is_us_country(country_value) or (
        not country_value and state_code in US_STATE_CODES
    )
    if city and is_us and state_code:
        return f"{city}, {state_code}"
    if city and country_value and not is_us:
        country_display = _format_country(country_value)
        if country_display:
            return f"{city}, {country_display}"
    return fallback


def _state_abbreviation(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    upper = cleaned.upper()
    if upper in US_STATE_CODES:
        return upper
    if upper in STATE_NAME_TO_CODE:
        return STATE_NAME_TO_CODE[upper]
    compact = re.sub(r"[^A-Z]", "", upper)
    if compact in US_STATE_CODES:
        return compact
    if compact in STATE_NAME_TO_CODE:
        return STATE_NAME_TO_CODE[compact]
    if compact in STATE_COMPACT_TO_CODE:
        return STATE_COMPACT_TO_CODE[compact]
    if compact in STATE_ALIAS_TO_CODE:
        return STATE_ALIAS_TO_CODE[compact]
    return None


def _is_us_country(value: str | None) -> bool:
    if not value:
        return False
    normalized = re.sub(r"[^A-Z]", "", value.upper())
    return normalized in US_COUNTRY_CODES


def _format_country(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper()
    return cleaned
