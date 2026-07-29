"""
Certificate Generator — Module 12 (D[138]–D[145])

Documented certificate types (exact DOCX text):
    D[140]  Certificate of Enrollment
    D[141]  Certificate of Completion
    D[142]  Certificate of Recognition
    D[143]  Certificate of Participation
    D[144]  Diploma
    D[145]  PDF Output

Rules applied:
    - PDF via ReportLab (D[027]) — same library already used by SF9 and ID Maker.
    - Page size: letter — same as SF9.
    - Date: automatically set to today at generation time (approved).
    - Signatory: blank line labelled "School Principal" (approved).
    - Recognition / Participation: accept caller-supplied free-text (approved).
    - Diploma: uses existing student / enrollment data only (approved).
    - No DepEd wording, no external education rules, no graduation conditions.
"""

import os
from datetime import date
from io import BytesIO

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    Image,
    Table,
    TableStyle,
)

# ── brand colours (maroon matches login / ID card) ──────────────────────────
MAROON = colors.HexColor("#7a1020")
GOLD   = colors.HexColor("#c8a84b")
DARK   = colors.HexColor("#1a1a1a")

# ── page margins (letter, same as SF9) ──────────────────────────────────────
PAGE_W, PAGE_H = letter
LEFT = RIGHT = 1.0 * inch
TOP  = BOTTOM = 0.75 * inch


# ── helpers ──────────────────────────────────────────────────────────────────

def _logo() -> Image | None:
    path = os.path.join(settings.BASE_DIR, "static", "images", "logo.jpg")
    if os.path.exists(path):
        return Image(path, width=0.9 * inch, height=0.9 * inch)
    return None


def _full_name(student) -> str:
    parts = [student.first_name]
    if student.middle_name:
        parts.append(f"{student.middle_name[0]}.")
    parts.append(student.last_name)
    if student.name_extension:
        parts.append(student.name_extension)
    return " ".join(p for p in parts if p)


def _get_enrollment(student):
    from enrollment.models import Enrollment
    return (
        Enrollment.objects
        .filter(student=student)
        .select_related("grade_level", "section", "school_year")
        .order_by("-school_year__is_active", "-date_enrolled")
        .first()
    )


def _today_str() -> str:
    d = date.today()
    return d.strftime("%B %d, %Y")


def _s(size: float, bold: bool = False,
        color=None, align=TA_CENTER) -> ParagraphStyle:
    """Shorthand style builder."""
    return ParagraphStyle(
        "_",
        fontSize=size,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        textColor=color or DARK,
        alignment=align,
        leading=size * 1.4,
    )


def _base_doc(buffer: BytesIO) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=TOP,
        bottomMargin=BOTTOM,
        leftMargin=LEFT,
        rightMargin=RIGHT,
    )


def _school_header(elements: list) -> None:
    """Common header: logo + school name + address block."""
    school_name = getattr(settings, "SCHOOL_NAME", "Mayorga National High School")
    address     = getattr(settings, "SCHOOL_ADDRESS", "Mayorga, Leyte")
    division    = getattr(settings, "SCHOOL_DIVISION", "Leyte")
    region      = getattr(settings, "SCHOOL_REGION", "VIII")

    logo = _logo()
    header_rows = [[
        logo if logo else Paragraph("", _s(10)),
        [
            Paragraph("Republic of the Philippines", _s(8, align=TA_LEFT)),
            Paragraph("Department of Education", _s(8, align=TA_LEFT)),
            Paragraph(f"Region {region} · Division of {division}", _s(8, align=TA_LEFT)),
            Paragraph(f"<b>{school_name}</b>", _s(10, bold=True, align=TA_LEFT)),
            Paragraph(address, _s(8, align=TA_LEFT)),
        ],
    ]]
    tbl = Table(header_rows, colWidths=[1.0 * inch, PAGE_W - LEFT - RIGHT - 1.0 * inch])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=2, color=MAROON))
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=MAROON))
    elements.append(Spacer(1, 0.35 * inch))


def _signature_block(elements: list) -> None:
    """Blank signature line labelled 'School Principal' (approved)."""
    elements.append(Spacer(1, 0.5 * inch))
    content_w = PAGE_W - LEFT - RIGHT
    sig_w = 2.5 * inch
    pad   = (content_w - sig_w) / 2

    sig = Table(
        [[Paragraph("", _s(10))]],
        colWidths=[sig_w],
    )
    sig.setStyle(TableStyle([
        ("LINEBELOW",    (0, 0), (-1, -1), 1, DARK),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))

    wrapper = Table([[sig]], colWidths=[content_w],
                    style=TableStyle([("LEFTPADDING",(0,0),(-1,-1), pad)]))
    elements.append(wrapper)
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("School Principal", _s(9, align=TA_CENTER)))


def _footer(elements: list) -> None:
    elements.append(Spacer(1, 0.25 * inch))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=MAROON))
    elements.append(Spacer(1, 4))
    elements.append(
        Paragraph(
            f"Issued on {_today_str()}  ·  "
            f"{getattr(settings,'SCHOOL_NAME','Mayorga National High School')}",
            _s(7, color=colors.grey),
        )
    )


def _build(elements: list) -> bytes:
    buffer = BytesIO()
    doc = _base_doc(buffer)
    doc.build(elements)
    return buffer.getvalue()


# ── Certificate title banner ─────────────────────────────────────────────────

def _cert_title(elements: list, title: str) -> None:
    elements.append(Paragraph(title, _s(20, bold=True, color=MAROON)))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(HRFlowable(width="60%", thickness=1, color=GOLD,
                                hAlign="CENTER"))
    elements.append(Spacer(1, 0.25 * inch))


# ── "This is to certify that" preamble ──────────────────────────────────────

def _certify_preamble(elements: list) -> None:
    elements.append(Paragraph("This is to certify that", _s(11)))
    elements.append(Spacer(1, 0.15 * inch))


def _student_name_block(elements: list, student) -> None:
    elements.append(
        Paragraph(_full_name(student).upper(),
                  _s(16, bold=True, color=MAROON))
    )
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(
        Paragraph(f"LRN: {student.lrn}", _s(9, color=colors.grey))
    )
    elements.append(Spacer(1, 0.2 * inch))


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC FUNCTIONS — one per certificate type
# ─────────────────────────────────────────────────────────────────────────────

def build_enrollment_cert(student) -> bytes:
    """
    Certificate of Enrollment (D[140]).
    States that the student is enrolled for the current / most recent school year.
    Uses only existing Student + Enrollment data.
    """
    enrollment = _get_enrollment(student)
    grade   = enrollment.grade_level.name if enrollment else "—"
    section = enrollment.section.name     if enrollment else "—"
    sy      = str(enrollment.school_year) if enrollment else "—"

    elements = []
    _school_header(elements)
    _cert_title(elements, "Certificate of Enrollment")
    _certify_preamble(elements)
    _student_name_block(elements, student)

    body = (
        f"is officially enrolled in <b>{grade}</b>, Section <b>{section}</b> "
        f"for School Year <b>{sy}</b> at "
        f"<b>{getattr(settings,'SCHOOL_NAME','Mayorga National High School')}</b>."
    )
    elements.append(Paragraph(body, _s(11, align=TA_JUSTIFY)))

    _signature_block(elements)
    _footer(elements)
    return _build(elements)


def build_completion_cert(student) -> bytes:
    """
    Certificate of Completion (D[141]).
    States that the student has completed the documented school year.
    Uses only existing Student + Enrollment data — no invented completion rules.
    """
    enrollment = _get_enrollment(student)
    grade = enrollment.grade_level.name if enrollment else "—"
    sy    = str(enrollment.school_year) if enrollment else "—"

    elements = []
    _school_header(elements)
    _cert_title(elements, "Certificate of Completion")
    _certify_preamble(elements)
    _student_name_block(elements, student)

    body = (
        f"has successfully completed <b>{grade}</b> "
        f"for School Year <b>{sy}</b> at "
        f"<b>{getattr(settings,'SCHOOL_NAME','Mayorga National High School')}</b>."
    )
    elements.append(Paragraph(body, _s(11, align=TA_JUSTIFY)))

    _signature_block(elements)
    _footer(elements)
    return _build(elements)


def build_recognition_cert(student, recognition_for: str) -> bytes:
    """
    Certificate of Recognition (D[142]).
    `recognition_for` is the free-text entered by the user — required,
    no default invented. Caller must supply a non-empty string.
    """
    enrollment = _get_enrollment(student)
    grade = enrollment.grade_level.name if enrollment else "—"
    sy    = str(enrollment.school_year) if enrollment else "—"

    elements = []
    _school_header(elements)
    _cert_title(elements, "Certificate of Recognition")
    _certify_preamble(elements)
    _student_name_block(elements, student)

    body = (
        f"is hereby recognized for <b>{recognition_for}</b> "
        f"in <b>{grade}</b>, School Year <b>{sy}</b> at "
        f"<b>{getattr(settings,'SCHOOL_NAME','Mayorga National High School')}</b>."
    )
    elements.append(Paragraph(body, _s(11, align=TA_JUSTIFY)))

    _signature_block(elements)
    _footer(elements)
    return _build(elements)


def build_participation_cert(student, participated_in: str) -> bytes:
    """
    Certificate of Participation (D[143]).
    `participated_in` is the free-text entered by the user — required,
    no default invented.
    """
    enrollment = _get_enrollment(student)
    grade = enrollment.grade_level.name if enrollment else "—"
    sy    = str(enrollment.school_year) if enrollment else "—"

    elements = []
    _school_header(elements)
    _cert_title(elements, "Certificate of Participation")
    _certify_preamble(elements)
    _student_name_block(elements, student)

    body = (
        f"actively participated in <b>{participated_in}</b> "
        f"in <b>{grade}</b>, School Year <b>{sy}</b> at "
        f"<b>{getattr(settings,'SCHOOL_NAME','Mayorga National High School')}</b>."
    )
    elements.append(Paragraph(body, _s(11, align=TA_JUSTIFY)))

    _signature_block(elements)
    _footer(elements)
    return _build(elements)


def build_diploma(student) -> bytes:
    """
    Diploma (D[144]).
    Uses existing student / enrollment data only.
    No graduation rules, no external DepEd conditions — per approved scope.
    """
    enrollment = _get_enrollment(student)
    grade   = enrollment.grade_level.name if enrollment else "—"
    section = enrollment.section.name     if enrollment else "—"
    sy      = str(enrollment.school_year) if enrollment else "—"

    elements = []
    _school_header(elements)
    _cert_title(elements, "DIPLOMA")
    _certify_preamble(elements)
    _student_name_block(elements, student)

    body = (
        f"having satisfactorily completed the requirements of <b>{grade}</b>, "
        f"Section <b>{section}</b>, School Year <b>{sy}</b> at "
        f"<b>{getattr(settings,'SCHOOL_NAME','Mayorga National High School')}</b>, "
        f"is hereby awarded this Diploma."
    )
    elements.append(Paragraph(body, _s(11, align=TA_JUSTIFY)))

    _signature_block(elements)
    _footer(elements)
    return _build(elements)
