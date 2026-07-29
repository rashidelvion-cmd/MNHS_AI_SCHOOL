from io import BytesIO

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)

from .services.sf9.data import build_sf9_data

PASSING_GRADE = 75


def _remark_for(final_grade):
    if final_grade is None:
        return "—"
    return "Passed" if final_grade >= PASSING_GRADE else "Failed"


def build_sf9_pdf(student, school_year):
    """
    Build the SF9 (Learner's Performance Report / Report Card) PDF for one
    student, for one school year, and return it as bytes.

    Adapts automatically to the school year's grading system:
    4 periods (Q1-Q4) or 3 periods (Term 1-3).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()
    center_style = ParagraphStyle("center", parent=styles["Normal"], alignment=1)
    title_style = ParagraphStyle("title", parent=styles["Heading1"], alignment=1, fontSize=14)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Heading2"], alignment=1, fontSize=12)

    elements = []

    elements.append(Paragraph("Republic of the Philippines", center_style))
    elements.append(Paragraph("Department of Education", center_style))
    elements.append(Paragraph(settings.SCHOOL_NAME, title_style))
    elements.append(Paragraph(settings.SCHOOL_ADDRESS, center_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("LEARNER'S REPORT CARD (SF9)", subtitle_style))
    elements.append(Spacer(1, 14))

    # --- Learner information (from the SF9 data source) ---
    data = build_sf9_data(student, school_year)
    grade_level = data["grade_level"].name if data["grade_level"] else "—"
    section = data["section"].name if data["section"] else "—"

    info_data = [
        ["Name:", str(student), "LRN:", student.lrn],
        ["Grade Level:", grade_level, "Section:", section],
        ["School Year:", str(school_year), "Grading System:", school_year.get_grading_system_display()],
    ]
    info_table = Table(info_data, colWidths=[1.1 * inch, 2.6 * inch, 1.1 * inch, 2.2 * inch])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(info_table)
    elements.append(Spacer(1, 16))

    # --- Grades table ---
    period_count = school_year.period_count
    period_headers = [school_year.period_label(n) for n in range(1, period_count + 1)]

    header_row = ["Learning Area"] + period_headers + ["General Average", "Remarks"]
    table_data = [header_row]

    subject_averages = []

    for entry in data["subjects"]:
        period_values = entry["periods"][:period_count]
        row = [entry["subject"].name]
        row += [f"{v}" if v is not None else "—" for v in period_values]
        row.append(f"{entry['final_grade']}" if entry["final_grade"] is not None else "—")
        row.append(entry["remarks"] or "—")
        table_data.append(row)

        if entry["final_grade"] is not None:
            subject_averages.append(entry["final_grade"])

    if len(table_data) == 1:
        table_data.append(["No grades recorded for this school year."] + [""] * (period_count + 1))

    col_widths = [2.3 * inch] + [0.7 * inch] * period_count + [1.1 * inch, 0.9 * inch]
    grades_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    grades_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(grades_table)
    elements.append(Spacer(1, 16))

    # --- General average + promotion status ---
    general_average = (
        data["general_average"] if data["general_average"] is not None else "—"
    )
    overall_status = data["eligible_for_promotion_text"] or "—"
    average_descriptor = data["general_average_descriptor"] or "—"

    summary_data = [
        ["General Average", str(general_average)],
        ["Descriptor", average_descriptor],
        ["Status", overall_status],
    ]
    summary_table = Table(summary_data, colWidths=[2.3 * inch, 2 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 12))

    # --- Attendance record (SF9 attendance block) ---
    attendance_rows = data["attendance_rows"]
    attendance_totals = data["attendance_totals"]
    attendance_data = [
        ["Month"] + [row["month_label"] for row in attendance_rows] + ["Total"],
        ["Class Days"]
        + [row["class_days"] for row in attendance_rows]
        + [attendance_totals["class_days"]],
        ["Days Present"]
        + [row["days_present"] for row in attendance_rows]
        + [attendance_totals["days_present"]],
        ["Days Absent"]
        + [row["days_absent"] for row in attendance_rows]
        + [attendance_totals["days_absent"]],
    ]
    attendance_table = Table(
        attendance_data,
        colWidths=[1.1 * inch] + [0.52 * inch] * len(attendance_rows) + [0.6 * inch],
    )
    attendance_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(attendance_table)
    elements.append(Spacer(1, 10))

    elements.append(
        Paragraph(
            f"Passing grade: {PASSING_GRADE}. Period grades are the official "
            "transmuted grades (DepEd Order No. 8, s. 2015) computed from the "
            "E-Class Record; Status reflects whether the learner passed every subject.",
            ParagraphStyle("note", parent=styles["Normal"], fontSize=7.5, textColor=colors.grey),
        )
    )

    elements.append(Spacer(1, 30))

    signature_data = [
        ["_____________________________", "_____________________________"],
        ["Class Adviser", "Principal"],
    ]
    signature_table = Table(signature_data, colWidths=[3 * inch, 3 * inch])
    signature_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
            ]
        )
    )
    elements.append(signature_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
