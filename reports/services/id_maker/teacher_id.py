"""
Teacher ID card PDF generator.

Documented requirements:
    D[134] Teacher ID
    D[135] QR Code
    D[137] uses employee_id as the natural teacher identifier
           (D[137] specifies student.lrn for students; employee_id
            is the direct equivalent for teachers per existing model)

Uses only existing Teacher model fields — no new DB fields or migrations.
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

CARD_W = 85.6 * mm
CARD_H = 54.0 * mm

MAROON = colors.HexColor("#7a1020")
GOLD   = colors.HexColor("#c8a84b")
WHITE  = colors.white
DARK   = colors.HexColor("#1a1a1a")
LIGHT  = colors.HexColor("#f5f5f5")
GREEN  = colors.HexColor("#1a5c2e")   # teacher cards use green accent


def _qr_image(data: str, size: float) -> Image:
    """Generate QR code image. For teachers, data = employee_id."""
    qr = qrcode.make(data)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=size, height=size)


def _school_logo(size: float):
    import os
    logo_path = os.path.join(settings.BASE_DIR, "static", "images", "logo.jpg")
    if os.path.exists(logo_path):
        return Image(logo_path, width=size, height=size)
    return None


def s(size, bold=False, color=None, align=TA_CENTER):
    if color is None:
        color = colors.white
    return ParagraphStyle("_", fontSize=size,
                          fontName="Helvetica-Bold" if bold else "Helvetica",
                          textColor=color, alignment=align, leading=size + 2)


def _card_table(teacher) -> Table:
    """
    Build one teacher ID card.
    Layout mirrors the student ID but uses green accent
    and shows teacher-specific fields.
    """
    school_name = getattr(settings, "SCHOOL_NAME", "Mayorga National High School")
    school_addr = getattr(settings, "SCHOOL_ADDRESS", "Mayorga, Leyte")
    division    = getattr(settings, "SCHOOL_DIVISION", "Leyte")

    # QR code from employee_id (teacher equivalent of student.lrn)
    qr_img = _qr_image(teacher.employee_id, 20 * mm)
    logo   = _school_logo(10 * mm)

    full_name = f"{teacher.last_name}, {teacher.first_name}"

    body_left = [
        Paragraph(full_name, s(7, bold=True, color=DARK, align=TA_LEFT)),
        Spacer(1, 2 * mm),
        Paragraph(f"Employee ID: {teacher.employee_id}", s(6, color=DARK, align=TA_LEFT)),
        Spacer(1, 1 * mm),
        Paragraph(school_name, s(5, color=DARK, align=TA_LEFT)),
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

    header_logo = logo if logo else Paragraph("", s(6))

    card = Table(
        [
            [header_logo,
             Paragraph(
                 f"<b>{school_name}</b><br/><font size='4'>{school_addr} · Division of {division}</font>",
                 s(5, color=WHITE))],
            [inner, ""],
            [Paragraph("FACULTY ID", s(7, bold=True)), ""],
        ],
        colWidths=[12 * mm, CARD_W - 12 * mm],
        rowHeights=[9 * mm, CARD_H - 18 * mm, 9 * mm],
    )
    card.setStyle(TableStyle([
        # Header band — green for teachers
        ("BACKGROUND",   (0, 0), (-1, 0), GREEN),
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
        ("BACKGROUND",   (0, 2), (-1, 2), GREEN),
        ("SPAN",         (0, 2), (-1, 2)),
        ("ALIGN",        (0, 2), (-1, 2), "CENTER"),
        ("VALIGN",       (0, 2), (-1, 2), "MIDDLE"),
        # Border
        ("BOX",          (0, 0), (-1, -1), 0.5, GREEN),
    ]))
    return card


def build_teacher_id_pdf(teachers) -> bytes:
    """
    Generate a PDF containing one ID card per teacher.
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
        title="Faculty ID Cards — MNHS",
    )

    elements = []
    for teacher in teachers:
        card = _card_table(teacher)
        elements.append(card)
        elements.append(Spacer(1, 6 * mm))

    doc.build(elements)
    return buffer.getvalue()
