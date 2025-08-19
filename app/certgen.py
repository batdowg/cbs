from __future__ import annotations

import hashlib
import os
from datetime import date
from io import BytesIO

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from utils.storage import ensure_dir, write_atomic


_MM = 72 / 25.4


def _mm(v: float) -> float:
    return v * _MM


def make_certificate_pdf(
    output_path: str,
    *,
    template_pdf: str = "app/assets/certificate_template.pdf",
    name: str,
    workshop: str,
    date: date,
) -> str:
    """Generate a certificate PDF and return its sha256 hash."""
    ensure_dir(os.path.dirname(output_path))

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, _ = A4

    # Name with autoshrink italic
    font_size = 48
    while font_size >= 32:
        c.setFont("Helvetica-Oblique", font_size)
        if c.stringWidth(name, "Helvetica-Oblique", font_size) <= width - _mm(40):
            break
        font_size -= 1
    c.drawCentredString(width / 2, _mm(145), name)

    # Workshop bold
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(width / 2, _mm(102), workshop)

    # Date
    c.setFont("Helvetica", 24)
    c.drawCentredString(width / 2, _mm(83), date.strftime("%d %B %Y").lstrip("0"))

    c.save()
    buffer.seek(0)

    template = PdfReader(template_pdf)
    overlay = PdfReader(buffer)
    base_page = template.pages[0]
    base_page.merge_page(overlay.pages[0])

    writer = PdfWriter()
    writer.add_page(base_page)
    out_buffer = BytesIO()
    writer.write(out_buffer)
    pdf_bytes = out_buffer.getvalue()

    write_atomic(output_path, pdf_bytes)

    return hashlib.sha256(pdf_bytes).hexdigest()
