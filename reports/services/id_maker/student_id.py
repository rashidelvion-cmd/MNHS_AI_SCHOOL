"""
Student ID card PDF generator.

Documented requirements:
    D[133] Student ID
    D[135] QR Code
    D[137] qrcode.make(student.lrn)   ← exact QR data source from DOCX

Uses only existing Student and Enrollment model fields — no new DB fields.
"""

from io import BytesIO

import qrcode
from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from enrollment.models import Enrollment

# CR80 standard ID card proportions (landscape): 85.6 mm × 54 mm
# We render two cards per A4 row, four rows per page = 8 cards/page.
CARD_W = 85.6 * mm
CARD_H = 54.0 * mm

# Brand colours matching login page and sidebar
MAROON  = colors.HexColor("#7a1020")
GOLD    = colors.HexColor("#c8a84b")
WHITE   = colors.white
DARK    = colors.HexColor("#1a1a1a")
LIGHT   = colors.HexColor("#f5f5f5")


def _qr_image(data: str, size: float) -> Image:
    """
    Generate a QR code image for `data` and return a ReportLab Image.
    Uses qrcode.make(data) exactly as documented in D[137].
    """
    qr = qrcode.make(data)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=size, height=size)


def _school_logo(size: float):
    """Return the MNHS logo as a ReportLab Image, or None if not found."""
    import os
    logo_path = os.path.join(settings.BASE_DIR, "static", "images", "logo.jpg")
    if os.path.exists(logo_path):
        return Image(logo_path, width=size, height=size)
    return None


def _get_enrollment(student):
    """Return the most recent / active enrollment for the student."""
    return (
        Enrollment.objects
        .filter(student=student)
        .select_related("grade_level", "section", "school_year")
        .order_by("-school_year__is_active", "-date_enrolled")
        .first()
    )


def _card_table(student, enrollment) -> Table:
    """
    Build one ID card as a ReportLab Table.
    Layout:
        ┌──────────────────────────────────────┐
        │  [logo]  SCHOOL NAME  REGION/DIV     │  ← header band (maroon)
        ├──────────────────────────────────────┤
        │                          ┌──────┐    │
        │  STUDENT NAME (bold)     │  QR  │    │
        │  LRN: xxxxxxxxxxxxxxxx   │      │    │
        │  Grade: __  Section: __  └──────┘    │
        │  SY: ___________                     │
        ├──────────────────────────────────────┤
        │              STUDENT ID              │  ← footer band
        └──────────────────────────────────────┘
    """
    school_name = getattr(settings, "SCHOOL_NAME", "Mayorga National High School")
    school_addr = getattr(settings, "SCHOOL_ADDRESS", "Mayorga, Leyte")
    division    = getattr(settings, "SCHOOL_DIVISION", "Leyte")

    # ── QR code — qrcode.make(student.lrn) per D[137] ──
    qr_img = _qr_image(student.lrn, 20 * mm)

    # ── Logo ──
    logo = _school_logo(10 * mm)

    # ── Styles ──
    def s(size, bold=False, color=WHITE, align=TA_CENTER):
        return ParagraphStyle("_", fontSize=size,
                              fontName="Helvetica-Bold" if bold else "Helvetica",
                              textColor=color, alignment=align, leading=size + 2)

    # ── Name ──
    full_name = f"{student.last_name}, {student.first_name}"
    if student.middle_name:
        full_name += f" {student.middle_name[0]}."
    if student.name_extension:
        full_name += f" {student.name_extension}"

    grade_txt   = enrollment.grade_level.name if enrollment else "—"
    section_txt = enrollment.section.name     if enrollment else "—"
    sy_txt      = str(enrollment.school_year) if enrollment else "—"

    # ── Header row ──
    header_logo_cell = logo if logo else Paragraph("", s(6))
    header_content = [
        header_logo_cell,
        [
            Paragraph(school_name, s(5, bold=True)),
            Paragraph(school_addr, s(4)),
            Paragraph(f"Division of {division}", s(4)),
        ],
    ]

    # ── Body ──
    body_left = [
        Paragraph(full_name, s(7, bold=True, color=DARK, align=TA_LEFT)),
        Spacer(1, 1 * mm),
        Paragraph(f"LRN: {student.lrn}", s(6, color=DARK, align=TA_LEFT)),
        Spacer(1, 1 * mm),
        Paragraph(f"{grade_txt} — {section_txt}", s(6, color=DARK, align=TA_LEFT)),
        Paragraph(f"SY {sy_txt}", s(6, color=DARK, align=TA_LEFT)),
    ]

    inner = Table(
        [[body_left, qr_img]],
        colWidths=[CARD_W * 0.62, CARD_W * 0.35],
    )
    inner.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING",(0, 0), (-1, -1), 2 * mm),
    ]))

    # ── Full card ──
    card = Table(
        [
            [header_logo_cell,
             Paragraph(
                 f"<b>{school_name}</b><br/><font size='4'>{school_addr} · Division of {division}</font>",
                 s(5, color=WHITE))],
            [inner, ""],
            [Paragraph("STUDENT ID", s(7, bold=True)), ""],
        ],
        colWidths=[12 * mm, CARD_W - 12 * mm],
        rowHeights=[9 * mm, CARD_H - 18 * mm, 9 * mm],
    )
    card.setStyle(TableStyle([
        # Header band
        ("BACKGROUND",   (0, 0), (-1, 0), MAROON),
        ("SPAN",         (0, 0), (-1, 0)),
        ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",       (0, 0), (-1, 0), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, 0), 2 * mm),
        # Body
        ("BACKGROUND",   (0, 1), (-1, 1), LIGHT),
        ("SPAN",         (0, 1), (-1, 1)),
        ("LEFTPADDING",  (0, 1), (-1, 1), 0),
        ("RIGHTPADDING", (0, 1), (-1, 1), 0),
        ("TOPPADDING",   (0, 1), (-1, 1), 2 * mm),
        # Footer band
        ("BACKGROUND",   (0, 2), (-1, 2), MAROON),
        ("SPAN",         (0, 2), (-1, 2)),
        ("ALIGN",        (0, 2), (-1, 2), "CENTER"),
        ("VALIGN",       (0, 2), (-1, 2), "MIDDLE"),
        # Border
        ("BOX",          (0, 0), (-1, -1), 0.5, MAROON),
    ]))
    return card


def build_student_id_pdf(students) -> bytes:
    """
    Generate a PDF containing one ID card per student.
    `students` is a queryset or list of Student instances.
    Returns raw PDF bytes.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        title="Student ID Cards — MNHS",
    )

    elements = []
    for student in students:
        enrollment = _get_enrollment(student)
        card = _card_table(student, enrollment)
        elements.append(card)
        elements.append(Spacer(1, 6 * mm))

    doc.build(elements)
    return buffer.getvalue()
