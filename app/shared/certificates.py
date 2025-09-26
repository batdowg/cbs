from __future__ import annotations

import os
import re
from datetime import date, datetime
from io import BytesIO
from typing import Iterable, NamedTuple, Sequence

from flask import current_app
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from sqlalchemy.exc import IntegrityError

from ..app import db
from ..models import (
    Certificate,
    CertificateTemplate,
    CertificateTemplateSeries,
    Language,
    Participant,
    ParticipantAccount,
    ParticipantAttendance,
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


_VALID_PAPER_SIZES = {"a4", "letter"}
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
    "certification_number",
)

_BADGE_EXTENSIONS: tuple[str, ...] = (".webp", ".png")

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


def _normalize_paper_size(paper_size: str | None) -> str:
    value = (paper_size or "").strip().lower()
    if value not in _VALID_PAPER_SIZES:
        raise ValueError(f"Unsupported paper size: {paper_size!r}")
    return value


def _normalize_language_code(lang_code: str | None) -> str:
    value = (lang_code or "").strip().lower().replace("_", "-")
    if not (2 <= len(value) <= 5) or not re.fullmatch(r"[a-z\-]+", value):
        raise ValueError(f"Unsupported language code: {lang_code!r}")
    return value


class TemplateResolution(NamedTuple):
    display_name: str
    path: str
    source: str
    paper: str
    language: str
    mtime: float


def _safe_template_path(assets_dir: str, candidate: str | None) -> str | None:
    raw = (candidate or "").strip()
    if not raw:
        return None
    assets_root = os.path.realpath(assets_dir)
    if os.path.isabs(raw):
        resolved = os.path.realpath(raw)
        if resolved == assets_root or resolved.startswith(f"{assets_root}{os.sep}"):
            return resolved
        return None
    resolved = os.path.realpath(os.path.join(assets_dir, raw))
    if resolved == assets_root or resolved.startswith(f"{assets_root}{os.sep}"):
        return resolved
    return None


def _normalized_template_language(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", "-")


def resolve_series_template(
    series_id: int, paper_size: str, lang_code: str
) -> TemplateResolution:
    normalized_size = _normalize_paper_size(paper_size)
    normalized_lang = _normalize_language_code(lang_code)
    assets_dir = os.path.join(current_app.root_path, "assets")

    templates = (
        db.session.query(CertificateTemplate)
        .filter(CertificateTemplate.series_id == series_id)
        .filter(db.func.lower(CertificateTemplate.size) == normalized_size)
        .all()
    )

    explicit_template: CertificateTemplate | None = None
    explicit_attempt: str | None = None
    explicit_display: str | None = None

    base_lang = normalized_lang.split("-")[0]
    fallback_lang_tokens = {"", "any", "default", "all", "*"}

    ranked_templates: list[tuple[int, CertificateTemplate]] = []
    for tmpl in templates:
        tmpl_lang = _normalized_template_language(tmpl.language)
        if tmpl_lang == normalized_lang:
            ranked_templates.append((0, tmpl))
        elif tmpl_lang == base_lang:
            ranked_templates.append((1, tmpl))
        elif tmpl_lang in fallback_lang_tokens:
            ranked_templates.append((2, tmpl))

    if ranked_templates:
        ranked_templates.sort(key=lambda item: (item[0], item[1].language or ""))
        explicit_template = ranked_templates[0][1]
        explicit_display = explicit_template.filename
        explicit_attempt = _safe_template_path(assets_dir, explicit_template.filename)
        if explicit_attempt and os.path.isfile(explicit_attempt):
            mtime = os.path.getmtime(explicit_attempt)
            resolution = TemplateResolution(
                display_name=os.path.basename(explicit_display),
                path=explicit_attempt,
                source="explicit",
                paper=normalized_size,
                language=normalized_lang,
                mtime=mtime,
            )
            _log_template_resolution(resolution)
            return resolution

    pattern_name = f"fncert_template_{normalized_size}_{normalized_lang}.pdf"
    pattern_path = _safe_template_path(assets_dir, pattern_name)
    if pattern_path and os.path.isfile(pattern_path):
        if explicit_template:
            current_app.logger.info(
                "[cert-template] explicit mapping missing; falling back source=pattern"
            )
        mtime = os.path.getmtime(pattern_path)
        resolution = TemplateResolution(
            display_name=pattern_name,
            path=pattern_path,
            source="pattern",
            paper=normalized_size,
            language=normalized_lang,
            mtime=mtime,
        )
        _log_template_resolution(resolution)
        return resolution

    legacy_name = f"fncert_{normalized_size}_{normalized_lang}.pdf"
    legacy_path = _safe_template_path(assets_dir, legacy_name)
    if legacy_path and os.path.isfile(legacy_path):
        if explicit_template:
            current_app.logger.info(
                "[cert-template] explicit mapping missing; falling back source=legacy"
            )
        mtime = os.path.getmtime(legacy_path)
        resolution = TemplateResolution(
            display_name=legacy_name,
            path=legacy_path,
            source="legacy",
            paper=normalized_size,
            language=normalized_lang,
            mtime=mtime,
        )
        _log_template_resolution(resolution)
        return resolution

    available = []
    if os.path.isdir(assets_dir):
        available = sorted(
            name
            for name in os.listdir(assets_dir)
            if name.lower().startswith("fncert") and name.lower().endswith(".pdf")
        )[:10]
    explicit_details: str
    if explicit_template:
        if explicit_attempt:
            explicit_details = explicit_attempt
        else:
            explicit_details = f"<invalid:{explicit_template.filename}>"
    else:
        explicit_details = "<not configured>"
    message = (
        "Certificate template not found for series={series_id} size={size} "
        "language={lang}; explicit={explicit}; pattern={pattern}; legacy={legacy}; "
        "available={available}"
    ).format(
        series_id=series_id,
        size=normalized_size,
        lang=normalized_lang,
        explicit=explicit_details,
        pattern=pattern_path or pattern_name,
        legacy=legacy_path or legacy_name,
        available=", ".join(available) if available else "<none>",
    )
    raise FileNotFoundError(message)


def _log_template_resolution(resolution: TemplateResolution) -> None:
    timestamp = datetime.fromtimestamp(resolution.mtime).strftime("%Y-%m-%d %H:%M")
    current_app.logger.info(
        "[cert-template] using path=%s paper=%s lang=%s mtime=%s source=%s",
        resolution.path,
        resolution.paper,
        resolution.language,
        timestamp,
        resolution.source,
    )


class CertificateAttendanceError(RuntimeError):
    """Raised when certificate generation is blocked by attendance rules."""


def _participant_has_full_attendance(session: Session, participant_id: int) -> bool:
    days = session.number_of_class_days or 0
    if session.materials_only or days <= 0:
        return True
    required_days = set(range(1, days + 1))
    attendance_rows = (
        db.session.query(
            ParticipantAttendance.day_index, ParticipantAttendance.attended
        )
        .filter(
            ParticipantAttendance.session_id == session.id,
            ParticipantAttendance.participant_id == participant_id,
        )
        .all()
    )
    if not attendance_rows:
        return False
    attended_days = {
        day_index for day_index, attended in attendance_rows if bool(attended)
    }
    return required_days.issubset(attended_days)


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


def _resolve_badge_series_code(
    session: Session, series: CertificateTemplateSeries | None
) -> str:
    candidates = [
        getattr(series, "code", None) if series else None,
        getattr(session.workshop_type, "cert_series", None)
        if session.workshop_type
        else None,
    ]
    for value in candidates:
        cleaned = (value or "").strip()
        if cleaned:
            return cleaned.upper()
    raise ValueError("Missing certificate series code for badge number generation")


def _extract_badge_counter(value: str | None, prefix: str) -> int | None:
    if not value:
        return None
    if not value.startswith(prefix):
        return None
    suffix = value[len(prefix) :]
    if not suffix.isdigit():
        return None
    try:
        return int(suffix)
    except ValueError:
        return None


def generate_badge_number(session: Session, series_code: str) -> str:
    cleaned_code = (series_code or "").strip().upper()
    if not cleaned_code:
        raise ValueError("Certificate series code required for badge number")
    reference_date = session.end_date or session.start_date or date.today()
    session_part = f"{int(session.id):05d}"
    year_part = f"{reference_date.year % 100:02d}"
    prefix = f"KT{cleaned_code}-{year_part}{session_part}"
    existing = (
        db.session.query(Certificate.certification_number)
        .filter(Certificate.session_id == session.id)
        .filter(Certificate.certification_number.like(f"{prefix}%"))
        .order_by(Certificate.certification_number.desc())
        .with_for_update()
        .first()
    )
    next_counter = 1
    if existing:
        latest = _extract_badge_counter(existing[0], prefix)
        if latest is not None and latest >= next_counter:
            next_counter = latest + 1
    return f"{prefix}{next_counter:02d}"


def _is_cert_number_conflict(error: IntegrityError) -> bool:
    if not isinstance(error, IntegrityError):
        return False
    details: str = ""
    if getattr(error, "orig", None) is not None:
        details = str(error.orig)
    if not details:
        details = str(error)
    lowered = details.lower()
    return "certification_number" in lowered


def _certificate_storage_paths(session: Session) -> tuple[str, str, str]:
    reference_date = session.end_date or session.start_date or date.today()
    year = reference_date.year
    site_root = current_app.config.get("SITE_ROOT", "/srv")
    cert_root = os.path.join(site_root, "certificates")
    rel_dir = os.path.join(str(year), str(session.id))
    abs_dir = os.path.join(cert_root, rel_dir)
    return cert_root, rel_dir, abs_dir


def _badge_output_paths(
    session: Session, badge_number: str
) -> tuple[str, str, str]:
    cert_root, rel_dir, abs_dir = _certificate_storage_paths(session)
    filename = f"{badge_number}.png"
    rel_path = os.path.join(rel_dir, filename)
    abs_path = os.path.join(cert_root, rel_path)
    return abs_path, rel_path, abs_dir


def _badge_asset_roots() -> tuple[str, ...]:
    raw_roots = [
        os.path.join(current_app.root_path, "assets", "badges"),
        os.path.join(
            current_app.root_path, "..", "data", "cert-assets", "badges"
        ),
    ]
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in raw_roots:
        resolved = os.path.realpath(candidate)
        if not os.path.isdir(resolved):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return tuple(normalized)


def _safe_badge_path(root: str, candidate: str | None) -> str | None:
    raw = (candidate or "").strip()
    if not raw:
        return None
    root_real = os.path.realpath(root)
    if os.path.isabs(raw):
        resolved = os.path.realpath(raw)
        if resolved == root_real or resolved.startswith(f"{root_real}{os.sep}"):
            return resolved
        return None
    resolved = os.path.realpath(os.path.join(root_real, raw))
    if resolved == root_real or resolved.startswith(f"{root_real}{os.sep}"):
        return resolved
    return None


def _badge_filename_candidates(
    series_code: str, explicit: str | None
) -> list[str]:
    candidates: list[str] = []

    def _append(name: str) -> None:
        raw = (name or "").strip()
        if not raw:
            return
        base, ext = os.path.splitext(raw)
        if ext:
            option = f"{base}{ext}"
            if option not in candidates:
                candidates.append(option)
            return
        for extension in _BADGE_EXTENSIONS:
            option = f"{raw}{extension}"
            if option not in candidates:
                candidates.append(option)

    if explicit:
        _append(explicit)

    normalized = (series_code or "").strip()
    lowered = normalized.lower()
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    compact = re.sub(r"[^a-z0-9]+", "", lowered)

    base_stems: list[str] = []
    for value in (lowered, hyphenated, compact):
        if value and value not in base_stems:
            base_stems.append(value)

    expanded: list[str] = []
    for stem in base_stems:
        variations = {
            stem,
            stem.replace("-", ""),
            stem.replace("-", "_"),
            stem.replace("_", ""),
        }
        for variant in variations:
            cleaned = variant.strip("-_")
            if cleaned and cleaned not in expanded:
                expanded.append(cleaned)

    suffixes = ("", "_badge", "-badge", "badge")
    with_suffix: list[str] = []
    for stem in expanded:
        for suffix in suffixes:
            candidate = f"{stem}{suffix}" if suffix else stem
            if candidate and candidate not in with_suffix:
                with_suffix.append(candidate)

    prefixed: list[str] = []
    for stem in with_suffix:
        if stem not in prefixed:
            prefixed.append(stem)
        if not stem.startswith("kt_"):
            prefixed_name = f"kt_{stem}"
            if prefixed_name not in prefixed:
                prefixed.append(prefixed_name)

    for stem in prefixed:
        _append(stem)

    return candidates


def _resolve_badge_source(series_code: str, explicit: str | None) -> str:
    candidates = _badge_filename_candidates(series_code, explicit)
    roots = _badge_asset_roots()
    for root in roots:
        for candidate in candidates:
            resolved = _safe_badge_path(root, candidate)
            if resolved and os.path.isfile(resolved):
                return resolved
    attempted = [
        os.path.join(root, name) for root in roots for name in candidates
    ]
    raise FileNotFoundError(
        f"Badge asset not found for series {series_code!r}; attempted {attempted}"
    )


def _render_badge_png(source_path: str, dest_path: str) -> None:
    resampling = getattr(Image, "Resampling", None)
    resample_filter = (
        resampling.LANCZOS if resampling is not None else Image.LANCZOS
    )
    with Image.open(source_path) as img:
        badge = img.convert("RGBA")
        badge.thumbnail((600, 600), resample_filter)
        canvas_image = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
        offset_x = (600 - badge.width) // 2
        offset_y = (600 - badge.height) // 2
        canvas_image.paste(badge, (offset_x, offset_y), badge)
        canvas_image.save(dest_path, format="PNG")


def write_badge_png_for_certificate(cert: Certificate) -> None:
    if not cert.certification_number:
        return
    session = cert.session or db.session.get(Session, cert.session_id)
    if not session:
        return

    mapping, _ = get_template_mapping(session)
    series = getattr(mapping, "series", None) if mapping else None
    series_code = _resolve_badge_series_code(session, series)
    badge_filename = getattr(mapping, "badge_filename", None) if mapping else None

    source_path = _resolve_badge_source(series_code, badge_filename)
    abs_path, _, output_dir = _badge_output_paths(
        session, cert.certification_number
    )
    if os.path.exists(abs_path):
        return

    ensure_dir(output_dir)
    _render_badge_png(source_path, abs_path)
    os.chmod(abs_path, 0o644)
    current_app.logger.info("[BADGE] wrote %s", abs_path)


def render_certificate(
    session: Session,
    participant_account: ParticipantAccount,
    layout_version: str = "v1",
) -> str:
    assets_dir = os.path.join(current_app.root_path, "assets")
    mapping, effective_size = get_template_mapping(session)
    series = mapping.series if mapping else None
    if not series and session.workshop_type and session.workshop_type.cert_series:
        series = (
            db.session.query(CertificateTemplateSeries)
            .filter(
                db.func.lower(CertificateTemplateSeries.code)
                == session.workshop_type.cert_series.lower()
            )
            .one_or_none()
        )
    if not series:
        raise ValueError("Missing certificate template mapping for session")
    series_code = _resolve_badge_series_code(session, series)
    language = (
        session.workshop_language
        or getattr(mapping, "language", None)
        or "en"
    )
    resolution = resolve_series_template(series.id, effective_size, language)
    template_path = resolution.path

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
    if not _participant_has_full_attendance(session, participant.id):
        current_app.logger.info(
            "[cert-gate] blocked generation: participant_id=%s session_id=%s reason=not_full_attendance",
            participant.id,
            session.id,
        )
        raise CertificateAttendanceError(
            "Full attendance required to generate certificate."
        )
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

    participant_id = participant.id
    cert = (
        db.session.query(Certificate)
        .filter_by(session_id=session.id, participant_id=participant_id)
        .one_or_none()
    )
    if not cert:
        cert = Certificate(session_id=session.id, participant_id=participant_id)
        db.session.add(cert)

    needs_badge_number = not bool(cert.certification_number)
    assigned_badge_number = False
    if needs_badge_number:
        cert.certification_number = generate_badge_number(session, series_code)
        assigned_badge_number = True
    certification_number = cert.certification_number

    base_reader = PdfReader(template_path)
    base_page = base_reader.pages[0]
    w = float(base_page.mediabox.width)
    h = float(base_page.mediabox.height)
    mm = lambda v: v * 72.0 / 25.4
    center_x = w / 2.0

    series_layout = sanitize_series_layout(series.layout_config)
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
        detail_lines = _build_details_lines(
            session,
            details_cfg.get("variables", []),
            certification_number=certification_number,
        )
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
            total_lines = len(detail_lines)
            for index, line in enumerate(detail_lines):
                y_pos = mm(DEFAULT_BOTTOM_MARGIN_MM) + (
                    total_lines - index - 1
                ) * line_spacing
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

    cert_root, rel_dir, abs_dir = _certificate_storage_paths(session)
    ensure_dir(abs_dir)
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

    def _apply_certificate_updates(target: Certificate) -> None:
        target.certificate_name = display_name
        target.workshop_name = workshop
        target.workshop_date = completion
        target.pdf_path = rel_path

    _apply_certificate_updates(cert)

    attempts = 0
    while True:
        try:
            db.session.commit()
            break
        except IntegrityError as exc:
            if attempts >= 1 or not (needs_badge_number and _is_cert_number_conflict(exc)):
                db.session.rollback()
                raise
            attempts += 1
            db.session.rollback()
            assigned_badge_number = False
            cert = (
                db.session.query(Certificate)
                .filter_by(session_id=session.id, participant_id=participant_id)
                .one_or_none()
            )
            if not cert:
                cert = Certificate(session_id=session.id, participant_id=participant_id)
                db.session.add(cert)
            _apply_certificate_updates(cert)
            if not cert.certification_number:
                cert.certification_number = generate_badge_number(session, series_code)
                assigned_badge_number = True
            needs_badge_number = not bool(cert.certification_number)
            certification_number = cert.certification_number
    certification_number = cert.certification_number
    should_write_badge = assigned_badge_number
    if certification_number:
        badge_abs_path, _, _ = _badge_output_paths(
            session, certification_number
        )
        if os.path.exists(badge_abs_path):
            should_write_badge = False
        else:
            should_write_badge = True
    if should_write_badge and certification_number:
        write_badge_png_for_certificate(cert)

    current_app.logger.info(
        "[CERT] email=%s session=%s path=%s",
        participant_account.email,
        session.id,
        rel_path,
    )
    return rel_path


def render_for_session(
    session_id: int, emails: Iterable[str] | None = None
) -> tuple[int, int, list[str]]:
    session = db.session.get(Session, session_id)
    if not session or getattr(session, "cancelled", False):
        return 0, 0, []
    q = (
        db.session.query(SessionParticipant)
        .join(Participant, SessionParticipant.participant_id == Participant.id)
        .filter(SessionParticipant.session_id == session_id)
    )
    if emails:
        emails = [e.lower() for e in emails]
        q = q.filter(db.func.lower(Participant.email).in_(emails))
    count = 0
    skipped = 0
    paths: list[str] = []
    for link in q.all():
        participant = db.session.get(Participant, link.participant_id)
        if not participant or not participant.account:
            continue
        try:
            rel_path = render_certificate(session, participant.account)
            count += 1
            paths.append(rel_path)
        except CertificateAttendanceError:
            skipped += 1
            continue
        except Exception:
            current_app.logger.exception(
                "[CERT-FAIL] email=%s session=%s", participant.email, session.id
            )
    return count, skipped, paths


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


def compose_detail_panel_lines(
    variables: Sequence[str],
    *,
    facilitators: str | None,
    location: str | None,
    dates: str | None,
    class_days: str | None,
    contact_hours: str | None,
    certification_number: str | None,
) -> list[str]:
    ordered = [var for var in DETAIL_RENDER_SEQUENCE if var in variables]
    if not ordered:
        return []
    selected = set(ordered)
    lines: list[str] = []
    if "facilitators" in selected and facilitators:
        lines.append(f"{DETAIL_LABELS['facilitators']}: {facilitators}")
    if "location_title" in selected and location:
        lines.append(location)
    if "dates" in selected and dates:
        lines.append(dates)
    class_value = class_days if "class_days" in selected else None
    contact_value = contact_hours if "contact_hours" in selected else None
    if class_value and contact_value:
        lines.append(
            f"{DETAIL_LABELS['class_days']}: {class_value} • {DETAIL_LABELS['contact_hours']}: {contact_value}"
        )
    else:
        if class_value:
            lines.append(f"{DETAIL_LABELS['class_days']}: {class_value}")
        if contact_value:
            lines.append(f"{DETAIL_LABELS['contact_hours']}: {contact_value}")
    if "certification_number" in selected and certification_number:
        lines.append(
            f"{DETAIL_LABELS['certification_number']}: {certification_number}"
        )
    return lines


def _build_details_lines(
    session: Session,
    variables: Sequence[str],
    *,
    certification_number: str | None,
) -> list[str]:
    ordered = [var for var in DETAIL_RENDER_SEQUENCE if var in variables]
    if not ordered:
        return []
    facilitators = _format_facilitators(session) if "facilitators" in ordered else None
    location = _format_location(session) if "location_title" in ordered else None
    dates = _format_session_dates(session) if "dates" in ordered else None
    class_days = _format_class_days(session) if "class_days" in ordered else None
    contact_hours = (
        _format_contact_hours(session) if "contact_hours" in ordered else None
    )
    return compose_detail_panel_lines(
        ordered,
        facilitators=facilitators,
        location=location,
        dates=dates,
        class_days=class_days,
        contact_hours=contact_hours,
        certification_number=(
            certification_number if "certification_number" in ordered else None
        ),
    )


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
