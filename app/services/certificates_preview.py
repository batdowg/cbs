import base64
import copy
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from io import BytesIO
from types import SimpleNamespace
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont
from flask import current_app
from PyPDF2 import PdfReader

from ..models import CertificateTemplate, CertificateTemplateSeries
from ..shared.certificates import (
    DEFAULT_BOTTOM_MARGIN_MM,
    DETAIL_LABELS,
    DETAIL_RENDER_SEQUENCE,
    DETAIL_SIZE_MAX_PERCENT,
    DETAIL_SIZE_MIN_PERCENT,
    DETAILS_FONT_SIZE_PT,
    DETAILS_LINE_SPACING_PT,
    LETTER_NAME_INSET_MM,
    _available_font_codes,
    _language_allowed_fonts,
    _resolve_font,
)
from ..shared.certificates_layout import (
    PAGE_HEIGHT_MM,
    filter_detail_variables,
    filter_font_codes,
    sanitize_series_layout,
)

_CACHE_TTL_SECONDS = 45
_POINT_PER_MM = 72.0 / 25.4
_PREVIEW_SCALE = 2.0
_NAME_GRAY = (64, 64, 64)
_TEXT_GRAY = (77, 77, 77)

_FONT_PATHS = {
    "Helvetica": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "Helvetica-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "Helvetica-Oblique": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "Helvetica-BoldOblique": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "Times-Roman": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "Times-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "Times-Italic": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "Times-BoldItalic": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "Courier": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "Courier-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "Courier-Oblique": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf",
    "Courier-BoldOblique": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf",
}
_DEFAULT_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


@dataclass(frozen=True)
class PreviewResult:
    image_base64: str
    warnings: tuple[str, ...]


_preview_cache: dict[str, tuple[float, PreviewResult]] = {}


def _build_cache_key(
    *,
    series_id: int,
    language: str,
    size: str,
    template_filename: str,
    template_mtime: float,
    layout: dict,
) -> str:
    layout_fingerprint = json.dumps(layout, sort_keys=True, separators=(",", ":"))
    raw = "|".join(
        [
            str(series_id),
            language,
            size,
            template_filename,
            f"{template_mtime:.6f}",
            layout_fingerprint,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _sample_details_lines(size: str, variables: Iterable[str]) -> list[str]:
    selected = [var for var in DETAIL_RENDER_SEQUENCE if var in variables]
    if not selected:
        return []
    facilitators_value = "Alex Smith; Jamie Doe"
    is_letter = size.upper() == "LETTER"
    location_value = "Sample City, NY" if is_letter else "Sample City, Canada"
    dates_value = "1–2 March 2026"
    class_days_value = "2"
    contact_hours_value = "14"

    lines: list[str] = []
    if "facilitators" in selected:
        lines.append(f"{DETAIL_LABELS['facilitators']}: {facilitators_value}")
    if "location_title" in selected:
        lines.append(location_value)
    if "dates" in selected:
        lines.append(dates_value)
    class_days = class_days_value if "class_days" in selected else None
    contact_hours = contact_hours_value if "contact_hours" in selected else None
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


def _render_background(template_path: str, scale: float) -> tuple[Image.Image, float, float]:
    reader = PdfReader(template_path)
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    canvas = Image.new(
        "RGB",
        (int(round(width * scale)), int(round(height * scale))),
        "white",
    )
    content = page.get_contents()
    if not isinstance(content, list):
        content = [content]
    commands = "".join(obj.get_object().get_data().decode("latin-1") for obj in content)
    pattern = re.compile(r"([\d\.\-\s]+)cm\s+/(Image\d+) Do")
    xobjects = page["/Resources"].get("/XObject") if page.get("/Resources") else None
    if xobjects:
        for match in pattern.finditer(commands):
            numbers = [float(x) for x in match.group(1).strip().split()]
            if len(numbers) != 6:
                continue
            a, b, c, d, e, f = numbers
            name = "/" + match.group(2)
            stream = xobjects.get(name)
            if not stream:
                continue
            stream_obj = stream.get_object()
            data = stream_obj.get_data()
            try:
                image = Image.open(BytesIO(data)).convert("RGB")
            except Exception:
                continue
            width_pt = abs(a)
            height_pt = abs(d)
            w_px = max(1, int(round(width_pt * scale)))
            h_px = max(1, int(round(height_pt * scale)))
            image = image.resize((w_px, h_px))
            if d > 0:
                y_top_pt = f + height_pt
            else:
                y_top_pt = f
            x_px = int(round(e * scale))
            y_px = int(round((height - y_top_pt) * scale))
            canvas.paste(image, (x_px, y_px))
    return canvas, width, height


def _font_path(pdf_font: str) -> str:
    return _FONT_PATHS.get(pdf_font) or _DEFAULT_FONT_PATH


def _load_font(pdf_font: str, size_px: int, warnings: list[str], line: str) -> ImageFont.FreeTypeFont:
    path = _font_path(pdf_font)
    try:
        return ImageFont.truetype(path, max(size_px, 1))
    except Exception:
        if path != _DEFAULT_FONT_PATH:
            warnings.append(
                f"{line.title()} font {pdf_font} unavailable for preview; using fallback rendering font."
            )
        return ImageFont.truetype(_DEFAULT_FONT_PATH, max(size_px, 1))


def _fit_text(
    text: str,
    pdf_font: str,
    max_pt: int,
    min_pt: int,
    max_width_pt: float,
    scale: float,
    warnings: list[str],
    line: str,
) -> tuple[ImageFont.FreeTypeFont, tuple[int, int, int, int]]:
    max_width_px = max_width_pt * scale
    for pt in range(max_pt, min_pt - 1, -1):
        size_px = max(int(round(pt * scale)), 1)
        font = _load_font(pdf_font, size_px, warnings, line)
        bbox = font.getbbox(text)
        width_px = bbox[2] - bbox[0]
        if width_px <= max_width_px or pt == min_pt:
            return font, bbox
    return _load_font(pdf_font, int(round(min_pt * scale)), warnings, line), (0, 0, 0, 0)


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    bbox: tuple[int, int, int, int],
    center_x_px: float,
    baseline_px: float,
    fill: tuple[int, int, int],
):
    text_width = bbox[2] - bbox[0]
    x_px = int(round(center_x_px - text_width / 2 - bbox[0]))
    y_px = int(round(baseline_px + bbox[1]))
    draw.text((x_px, y_px), text, font=font, fill=fill)


def _draw_aligned(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    bbox: tuple[int, int, int, int],
    baseline_px: float,
    anchor_x_px: float,
    align: str,
    fill: tuple[int, int, int],
):
    text_width = bbox[2] - bbox[0]
    if align == "left":
        x_px = int(round(anchor_x_px - bbox[0]))
    else:
        x_px = int(round(anchor_x_px - text_width - bbox[0]))
    y_px = int(round(baseline_px + bbox[1]))
    draw.text((x_px, y_px), text, font=font, fill=fill)


def generate_preview(
    series: CertificateTemplateSeries,
    *,
    language: str,
    size: str,
    layout: dict,
) -> PreviewResult:
    matching_template = next(
        (
            tmpl
            for tmpl in series.templates
            if tmpl.language == language and tmpl.size == size
        ),
        None,
    )
    if not matching_template:
        raise ValueError("No template PDF configured for the selected language and size.")

    template_path = os.path.join(current_app.root_path, "assets", matching_template.filename)
    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f"Template file {matching_template.filename} is missing from assets/"
        )
    template_mtime = os.path.getmtime(template_path)

    cache_key = _build_cache_key(
        series_id=series.id,
        language=language,
        size=size,
        template_filename=matching_template.filename,
        template_mtime=template_mtime,
        layout=layout,
    )

    cached = _preview_cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    background, page_width, page_height = _render_background(template_path, _PREVIEW_SCALE)
    draw = ImageDraw.Draw(background)

    allowed_fonts = _language_allowed_fonts(language)
    available_fonts = _available_font_codes()
    warnings: list[str] = []
    session_stub = SimpleNamespace(id=f"series-{series.id}", workshop_language=language)

    def resolve_font(preferred: str, line: str) -> str:
        return _resolve_font(
            preferred,
            allowed_fonts,
            available_fonts,
            session_stub,
            size,
            line,
            warnings,
        )

    name_font_code = resolve_font(layout["name"]["font"], "name")
    workshop_font_code = resolve_font(layout["workshop"]["font"], "workshop")
    date_font_code = resolve_font(layout["date"]["font"], "date")

    center_x_px = (page_width * _PREVIEW_SCALE) / 2.0

    display_name = "Sample Learner Name"
    workshop_name = series.name or "Sample Workshop"
    completion_text = "31 December 2025"

    def mm_to_pt(mm_value: float) -> float:
        return mm_value * _POINT_PER_MM

    def baseline_px_from_mm(mm_value: float) -> float:
        y_pt = mm_to_pt(mm_value)
        return (page_height - y_pt) * _PREVIEW_SCALE

    base_name_width = page_width - mm_to_pt(40)
    name_width = base_name_width
    if size.upper() == "LETTER":
        name_width -= mm_to_pt(2 * LETTER_NAME_INSET_MM)
    name_font, name_bbox = _fit_text(
        display_name,
        name_font_code,
        48,
        32,
        name_width,
        _PREVIEW_SCALE,
        warnings,
        "name",
    )
    name_baseline_px = baseline_px_from_mm(layout["name"]["y_mm"])
    _draw_centered(draw, display_name, name_font, name_bbox, center_x_px, name_baseline_px, _NAME_GRAY)

    workshop_font, workshop_bbox = _fit_text(
        workshop_name,
        workshop_font_code,
        40,
        28,
        page_width - mm_to_pt(40),
        _PREVIEW_SCALE,
        warnings,
        "workshop",
    )
    workshop_baseline_px = baseline_px_from_mm(layout["workshop"]["y_mm"])
    _draw_centered(draw, workshop_name, workshop_font, workshop_bbox, center_x_px, workshop_baseline_px, _TEXT_GRAY)

    date_font = _load_font(date_font_code, int(round(20 * _PREVIEW_SCALE)), warnings, "date")
    date_bbox = date_font.getbbox(completion_text)
    date_baseline_px = baseline_px_from_mm(layout["date"]["y_mm"])
    _draw_centered(draw, completion_text, date_font, date_bbox, center_x_px, date_baseline_px, _TEXT_GRAY)

    details_cfg = layout.get("details", {})
    if details_cfg.get("enabled"):
        detail_lines = _sample_details_lines(size, details_cfg.get("variables", []))
        if detail_lines:
            detail_font_code = resolve_font(date_font_code, "details")
            try:
                size_percent_int = int(details_cfg.get("size_percent", DETAIL_SIZE_MAX_PERCENT))
            except (TypeError, ValueError):
                size_percent_int = DETAIL_SIZE_MAX_PERCENT
            if size_percent_int < DETAIL_SIZE_MIN_PERCENT or size_percent_int > DETAIL_SIZE_MAX_PERCENT:
                size_percent_int = max(
                    DETAIL_SIZE_MIN_PERCENT,
                    min(size_percent_int, DETAIL_SIZE_MAX_PERCENT),
                )
            scale_factor = size_percent_int / 100.0
            detail_font_size_pt = DETAILS_FONT_SIZE_PT * scale_factor
            detail_font = _load_font(
                detail_font_code,
                int(round(detail_font_size_pt * _PREVIEW_SCALE)),
                warnings,
                "details",
            )
            margin_pt = mm_to_pt(DEFAULT_BOTTOM_MARGIN_MM)
            line_spacing_px = DETAILS_LINE_SPACING_PT * scale_factor * _PREVIEW_SCALE
            for index, line in enumerate(detail_lines):
                baseline_pt = mm_to_pt(DEFAULT_BOTTOM_MARGIN_MM) + index * DETAILS_LINE_SPACING_PT * scale_factor
                baseline_px = (page_height - baseline_pt) * _PREVIEW_SCALE
                bbox = detail_font.getbbox(line)
                if details_cfg.get("side", "LEFT") == "RIGHT":
                    anchor_x = (page_width - margin_pt) * _PREVIEW_SCALE
                    _draw_aligned(draw, line, detail_font, bbox, baseline_px, anchor_x, "right", _TEXT_GRAY)
                else:
                    anchor_x = margin_pt * _PREVIEW_SCALE
                    _draw_aligned(draw, line, detail_font, bbox, baseline_px, anchor_x, "left", _TEXT_GRAY)

    buffer = BytesIO()
    background.save(buffer, format="PNG")
    image_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    result = PreviewResult(image_base64=image_base64, warnings=tuple(warnings))
    _preview_cache[cache_key] = (now, result)
    return result


def sanitize_layout_for_preview(
    series: CertificateTemplateSeries,
    *,
    size: str,
    override: dict | None,
) -> dict:
    series_layout = sanitize_series_layout(series.layout_config)
    size_key = size.upper()
    base_layout = copy.deepcopy(
        series_layout.get(size_key, series_layout.get("A4"))
    )
    if not override:
        return base_layout

    layout = {
        "name": {
            "font": base_layout["name"]["font"],
            "y_mm": base_layout["name"]["y_mm"],
        },
        "workshop": {
            "font": base_layout["workshop"]["font"],
            "y_mm": base_layout["workshop"]["y_mm"],
        },
        "date": {
            "font": base_layout["date"]["font"],
            "y_mm": base_layout["date"]["y_mm"],
        },
        "details": dict(base_layout.get("details", {})),
    }

    for key in ("name", "workshop", "date"):
        raw = override.get(key) if isinstance(override, dict) else None
        if isinstance(raw, dict):
            font = raw.get("font")
            if isinstance(font, str):
                filtered = filter_font_codes([font])
                if filtered:
                    layout[key]["font"] = filtered[0]
            try:
                y_val = float(raw.get("y_mm"))
            except (TypeError, ValueError):
                y_val = None
            if y_val is not None:
                max_y = PAGE_HEIGHT_MM.get(size_key, PAGE_HEIGHT_MM["A4"])
                if y_val < 0:
                    y_val = 0.0
                if y_val > max_y:
                    y_val = max_y
                layout[key]["y_mm"] = y_val

    details_raw = override.get("details") if isinstance(override, dict) else None
    if isinstance(details_raw, dict):
        layout["details"] = dict(base_layout.get("details", {}))
        layout["details"]["enabled"] = bool(details_raw.get("enabled"))
        side_val = str(details_raw.get("side", layout["details"].get("side", "LEFT"))).upper()
        if side_val in {"LEFT", "RIGHT"}:
            layout["details"]["side"] = side_val
        variables = details_raw.get("variables")
        if isinstance(variables, Iterable):
            layout["details"]["variables"] = filter_detail_variables(
                [str(var) for var in variables if isinstance(var, str)]
            )
        try:
            size_percent = int(details_raw.get("size_percent"))
        except (TypeError, ValueError):
            size_percent = layout["details"].get("size_percent", DETAIL_SIZE_MAX_PERCENT)
        if size_percent < DETAIL_SIZE_MIN_PERCENT:
            size_percent = DETAIL_SIZE_MIN_PERCENT
        if size_percent > DETAIL_SIZE_MAX_PERCENT:
            size_percent = DETAIL_SIZE_MAX_PERCENT
        layout["details"]["size_percent"] = size_percent

    return layout
