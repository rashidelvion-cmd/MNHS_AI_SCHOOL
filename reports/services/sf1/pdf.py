"""
SF1-SHS PDF generator — D[063] Print SF1 PDF.

Produces a landscape-letter PDF containing the same learner data as
the official SF1-SHS Excel export:
  • School header (name, ID, district, division, region, SY, grade, strand, section)
  • Male learners table
  • Female learners table
  • Totals row

Data source: same Enrollment query used by build_sf1_workbook (exporter.py).
Field order matches LEARNER_CELLS in exporter.py exactly.
ReportLab pattern follows reports/sf9.py and reports/services/certificates/generator.py.
"""

from __future__ import annotations

import datetime
from io import BytesIO

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from enrollment.models import Enrollment

# ── Brand colours (consistent with existing PDF outputs) ─────────────────────
MAROON = colors.HexColor("#7a1020")
DARK   = colors.HexColor("#1a1a1a")
LIGHT  = colors.HexColor("#f0f0f0")
WHITE  = colors.white

PAGE_W, PAGE_H = landscape(letter)
L_MARGIN = R_MARGIN = 0.4 * inch
T_MARGIN = B_MARGIN = 0.4 * inch


# ── Shared helpers (mirror exporter.py — no shared import to keep services independent) ──

def _official_name(student) -> str:
    parts = [student.last_name or "", student.first_name or ""]
    name = f"{parts[0]}, {parts[1]}".strip(", ")
    if student.name_extension:
        name += f" {student.name_extension}"
    if student.middle_name:
        name += f", {student.middle_name}"
    return name.upper()


def _age_on(birth_date, as_of) -> str:
    if not birth_date:
        return ""
    years = as_of.year - birth_date.year - (
        (as_of.month, as_of.day) < (birth_date.month, birth_date.day)
    )
    return str(years)


def _row_values(student, index: int, as_of: datetime.date) -> list:
    """Return one learner's data as an ordered list matching the PDF column headers."""
    return [
        str(index),
        student.lrn or "",
        _official_name(student),
        "M" if student.gender == "Male" else "F",
        student.birth_date.strftime("%m/%d/%Y") if student.birth_date else "",
        _age_on(student.birth_date, as_of),
        student.religious_affiliation or "",
        student.house_street or "",
        student.barangay or "",
        student.municipality or "",
        student.province or "",
        student.father_name or "",
        student.mother_maiden_name or "",
        student.guardian_name or "",
        student.guardian_relationship or "",
        student.contact_number or "",
        student.remarks_code or "",
    ]


# ── Column definitions ────────────────────────────────────────────────────────

COLUMNS = [
    ("#",                    0.22 * inch),
    ("LRN",                  0.82 * inch),
    ("Name\n(Last, First, Ext, Middle)", 1.35 * inch),
    ("Sex",                  0.22 * inch),
    ("Birthdate\n(mm/dd/yyyy)", 0.62 * inch),
    ("Age",                  0.22 * inch),
    ("Religious\nAffiliation", 0.55 * inch),
    ("House/Street/\nSitio/Purok", 0.65 * inch),
    ("Barangay",             0.55 * inch),
    ("Municipality/\nCity",  0.55 * inch),
    ("Province",             0.50 * inch),
    ("Father's Name",        0.75 * inch),
    ("Mother's\nMaiden Name", 0.75 * inch),
    ("Guardian\nName",       0.65 * inch),
    ("Guardian\nRelationship", 0.52 * inch),
    ("Contact\nNumber",      0.55 * inch),
    ("Remarks",              0.42 * inch),
]

COL_HEADERS = [c[0] for c in COLUMNS]
COL_WIDTHS  = [c[1] for c in COLUMNS]


# ── Style helpers ─────────────────────────────────────────────────────────────

def _s(size: float, bold: bool = False, color=None, align=TA_CENTER) -> ParagraphStyle:
    return ParagraphStyle(
        "_",
        fontSize=size,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        textColor=color or DARK,
        alignment=align,
        leading=size * 1.35,
    )


def _learner_table(students, label: str, as_of: datetime.date) -> list:
    """Return a list of flowables for one gender block (header + rows + summary)."""
    elements = []

    # Section label
    elements.append(Paragraph(
        f"<b>{label} LEARNERS</b>",
        _s(7, bold=True, color=MAROON, align=TA_LEFT),
    ))
    elements.append(Spacer(1, 2))

    # Build table data
    header = [Paragraph(h, _s(5.5, bold=True)) for h in COL_HEADERS]
    rows   = [header]
    for i, student in enumerate(students, start=1):
        row = _row_values(student, i, as_of)
        rows.append([Paragraph(str(v), _s(5.5)) for v in row])

    if not students:
        no_data = [Paragraph("—", _s(5.5))] * len(COL_HEADERS)
        rows.append(no_data)

    tbl = Table(rows, colWidths=COL_WIDTHS, repeatRows=1)
    tbl.setStyle(TableStyle([
        # Header band
        ("BACKGROUND",    (0, 0), (-1, 0), MAROON),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 5.5),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        # Body alternating rows
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT]),
        ("FONTSIZE",      (0, 1), (-1, -1), 5.5),
        ("ALIGN",         (0, 0), (0, -1),  "CENTER"),   # #
        ("ALIGN",         (1, 0), (1, -1),  "CENTER"),   # LRN
        ("ALIGN",         (3, 0), (5, -1),  "CENTER"),   # Sex/Birthdate/Age
        # Grid
        ("GRID",          (0, 0), (-1, -1), 0.25, colors.grey),
        ("TOPPADDING",    (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING",   (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 4))
    return elements


# ── Public function ───────────────────────────────────────────────────────────

def build_sf1_pdf(
    school_year,
    grade_level,
    section,
    semester_label: str,
) -> bytes:
    """
    Generate the SF1-SHS PDF for a section and return raw bytes.

    Parameters match build_sf1_workbook() exactly so the view can call
    both with the same arguments.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        topMargin=T_MARGIN,
        bottomMargin=B_MARGIN,
        leftMargin=L_MARGIN,
        rightMargin=R_MARGIN,
        title=f"SF1 {section} {school_year}",
    )

    elements = []

    # ── Page header ──────────────────────────────────────────────────────────
    elements.append(Paragraph("Republic of the Philippines", _s(7)))
    elements.append(Paragraph("Department of Education", _s(7)))
    elements.append(Paragraph(
        f"<b>{getattr(settings, 'SCHOOL_NAME', 'Mayorga National High School')}</b>",
        _s(9, bold=True),
    ))
    elements.append(Paragraph(
        getattr(settings, "SCHOOL_ADDRESS", "Mayorga, Leyte"), _s(7)
    ))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        "<b>School Form 1 — School Register for Senior High School (SF1-SHS)</b>",
        _s(10, bold=True, color=MAROON),
    ))
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=MAROON))
    elements.append(Spacer(1, 3))

    # ── Sub-header: SY / GL / Section / Semester ────────────────────────────
    meta_rows = [[
        Paragraph(f"<b>School Year:</b> {school_year}", _s(7, align=TA_LEFT)),
        Paragraph(f"<b>Grade Level:</b> {grade_level.name}", _s(7, align=TA_LEFT)),
        Paragraph(f"<b>Section:</b> {section.name}", _s(7, align=TA_LEFT)),
        Paragraph(f"<b>Semester:</b> {semester_label}", _s(7, align=TA_LEFT)),
        Paragraph(f"<b>Track/Strand:</b> {section.track_strand or '—'}", _s(7, align=TA_LEFT)),
        Paragraph(
            f"<b>Division:</b> {getattr(settings, 'SCHOOL_DIVISION', '')}  "
            f"<b>Region:</b> {getattr(settings, 'SCHOOL_REGION', '')}",
            _s(7, align=TA_LEFT),
        ),
    ]]
    content_w = PAGE_W - L_MARGIN - R_MARGIN
    meta_tbl = Table(meta_rows, colWidths=[content_w / 6] * 6)
    meta_tbl.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 2),
    ]))
    elements.append(meta_tbl)
    elements.append(Spacer(1, 5))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    elements.append(Spacer(1, 6))

    # ── Learner data ─────────────────────────────────────────────────────────
    as_of = datetime.date.today()
    enrollments = (
        Enrollment.objects
        .filter(school_year=school_year, section=section)
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    students = [e.student for e in enrollments]
    males   = [s for s in students if s.gender == "Male"]
    females = [s for s in students if s.gender != "Male"]

    elements.extend(_learner_table(males,   "MALE",   as_of))
    elements.extend(_learner_table(females, "FEMALE", as_of))

    # ── Totals ───────────────────────────────────────────────────────────────
    totals_tbl = Table([[
        Paragraph(f"<b>Total Male:</b> {len(males)}", _s(7, align=TA_LEFT)),
        Paragraph(f"<b>Total Female:</b> {len(females)}", _s(7, align=TA_LEFT)),
        Paragraph(f"<b>Grand Total:</b> {len(students)}", _s(7, align=TA_LEFT)),
    ]], colWidths=[content_w / 3] * 3)
    totals_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
    ]))
    elements.append(totals_tbl)

    doc.build(elements)
    return buffer.getvalue()
