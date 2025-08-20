import os, math, datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfReader, PdfWriter

TEMPLATE_PATH = "/app/assets/certificate_template.pdf"  # empty template as per instructions
OUT_DIR = "/srv/certificates/_samples"
OUT_PATH = os.path.join(OUT_DIR, "sample.pdf")

# Ensure output folder exists
os.makedirs(OUT_DIR, exist_ok=True)

# Page size: derive from template if possible, else fallback to letter
try:
    base = PdfReader(open(TEMPLATE_PATH, "rb"))
    first = base.pages[0]
    media = first.mediabox
    width = float(media.right - media.left)
    height = float(media.top - media.bottom)
    page_size = (width, height)
except Exception:
    page_size = letter

# Register fonts (use built-ins if TTFs are unavailable)
try:
    # If DejaVu fonts are available in the image, you can register them here later.
    pass
except Exception:
    pass

# Sample data per your A–G decisions
name = "Jordan A. Participant"
workshop_cert_name = "Problem Solving & Decision Making"
# Date uses session end date; use today as stand-in
date_text = datetime.date.today().strftime("%-d %B %Y") if hasattr(datetime.date.today(), 'strftime') else datetime.date.today().strftime("%d %B %Y")

# Create an overlay PDF with text at exact positions
overlay_path = os.path.join(OUT_DIR, "_overlay.pdf")
c = canvas.Canvas(overlay_path, pagesize=page_size)

# Layout rules:
# Name: Y from bottom 145 mm, italic, autoshrink 48 -> 32 pt, centered
# Workshop: Y 102 mm, larger font (use 36 pt), centered
# Date: Y 83 mm, format d Month YYYY, centered
page_w, page_h = page_size

def draw_centered_text(text, y_mm_from_bottom, font_name, font_size):
    c.setFont(font_name, font_size)
    text_w = c.stringWidth(text, font_name, font_size)
    c.drawString((page_w - text_w) / 2.0, y_mm_from_bottom * mm, text)

# Name autoshrink
name_font = "Times-Italic"
size = 48
while size > 32:
    cw = pdfmetrics.stringWidth(name, name_font, size)
    if cw <= page_w * 0.86:  # allow 7% margins on each side
        break
    size -= 1
draw_centered_text(name, 145, name_font, size)

# Workshop line
draw_centered_text(workshop_cert_name, 102, "Helvetica", 36)

# Date line
draw_centered_text(date_text, 83, "Helvetica", 18)

c.showPage()
c.save()

# Merge overlay onto template
base_reader = PdfReader(open(TEMPLATE_PATH, "rb"))
overlay_reader = PdfReader(open(overlay_path, "rb"))
writer = PdfWriter()

page0 = base_reader.pages[0]
page0.merge_page(overlay_reader.pages[0])
writer.add_page(page0)

with open(OUT_PATH, "wb") as f:
    writer.write(f)

print(f"OK {OUT_PATH}")
