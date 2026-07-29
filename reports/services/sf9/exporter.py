"""
Official SF9 (Learner's Performance Report / Report Card) Excel export.

Fills a pristine copy of the bundled official template
(reports/templates_xlsx/SF9_SHS.xlsx, sheet "SF9_3Terms") from the SF9
data source. The data source is used as-is: this module never computes a
grade of its own.

Verified template geometry (print area P32:AQ82):

    school block    P35 region, P36 division, P37 district, P38 address,
                    P40 school name, P44 "School Year: ..."
    learner block   Q46 name, T46 age, W46 sex,
                    Q47 LRN, T47 grade, W47 section, R48 track/strand
    grades table    rows 60..72 -> P subject, S/T/U terms 1..3,
                    V final grade, W remarks
    general average row 73 -> V value, W Promoted/Retained
    attendance      AE..AN = Jun..Mar, AQ = TOTAL,
                    row 36 class days, row 38 present, row 40 absent
    transfer block  AE67 admitted to grade, AG68 eligible for admission,
                    AK71/AK72 adviser + position,
                    AD73/AD74 principal + position
    cancellation    AD80/AD81 principal + position

Teacher's comments, parent's signature and the cancellation date are left
blank for handwriting (no data source exists for them).
"""

from __future__ import annotations

import datetime
from pathlib import Path

import openpyxl
from django.conf import settings

from .data import build_sf9_data

TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "templates_xlsx" / "SF9_SHS.xlsx"
)

SHEET_NAME = "SF9_3Terms"

REQUIRED_PERIOD_COUNT = 3          # the sheet has exactly 3 term columns
FIRST_SUBJECT_ROW = 60
LAST_SUBJECT_ROW = 72
SUBJECT_CAPACITY = LAST_SUBJECT_ROW - FIRST_SUBJECT_ROW + 1   # 13
GENERAL_AVERAGE_ROW = 73

SUBJECT_COL = "P"
TERM_COLS = ("S", "T", "U")
FINAL_COL = "V"
REMARKS_COL = "W"

# Attendance: Jun..Mar map to AE..AN; AQ is the TOTAL column.
ATTENDANCE_MONTH_COLS = ["AE", "AF", "AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN"]
ATTENDANCE_TOTAL_COL = "AQ"
CLASS_DAYS_ROW = 36
DAYS_PRESENT_ROW = 38
DAYS_ABSENT_ROW = 40


class SF9ExportError(Exception):
    """Raised when the learner/school year cannot produce a valid SF9."""


def _learner_name(student):
    """SF9 prints the name as First Middle Last (per the official sample)."""
    parts = [student.first_name or "", student.middle_name or "", student.last_name or ""]
    name = " ".join(part for part in parts if part).strip()
    if student.name_extension:
        name = f"{name} {student.name_extension}".strip()
    return name.upper()


def _age_on(birth_date, as_of):
    if not birth_date:
        return ""
    return as_of.year - birth_date.year - (
        (as_of.month, as_of.day) < (birth_date.month, birth_date.day)
    )


def build_sf9_workbook(student, school_year, options=None):
    """
    Returns (openpyxl.Workbook, warnings: list[str]).

    Raises SF9ExportError when the school year is not 3-term or the learner
    has no enrollment for it.

    ``options`` (all optional, free text — no schema): adviser_name,
    adviser_position, principal_name, principal_position,
    admitted_to_grade, eligible_for_admission_to_grade.
    """
    options = options or {}
    warnings = []

    if school_year.period_count != REQUIRED_PERIOD_COUNT:
        raise SF9ExportError(
            f"{school_year} uses {school_year.get_grading_system_display()}, but the "
            "official SF9 sheet provided by the school has exactly three term "
            "columns. Only 3-term school years can be exported with this form."
        )

    data = build_sf9_data(student, school_year)

    if data["enrollment"] is None:
        raise SF9ExportError(
            f"{student} has no enrollment for {school_year} — the SF9 needs the "
            "learner's grade level and section. Import or encode the SF1 first."
        )

    workbook = openpyxl.load_workbook(TEMPLATE_PATH)
    worksheet = workbook[SHEET_NAME]

    # ---------------- school block ----------------
    worksheet["P35"] = f"Region {getattr(settings, 'SCHOOL_REGION', '')}".strip()
    division = getattr(settings, "SCHOOL_DIVISION", "")
    worksheet["P36"] = f"DIVISION OF {division}".upper() if division else ""
    worksheet["P37"] = getattr(settings, "SCHOOL_DISTRICT", "")
    worksheet["P38"] = settings.SCHOOL_ADDRESS
    worksheet["P40"] = settings.SCHOOL_NAME
    worksheet["P44"] = f"School Year:  {school_year}"

    # ---------------- learner block ----------------
    today = datetime.date.today()
    worksheet["Q46"] = _learner_name(student)
    worksheet["T46"] = _age_on(student.birth_date, today)
    worksheet["W46"] = student.gender or ""
    worksheet["Q47"] = student.lrn
    worksheet["T47"] = data["grade_level"].name if data["grade_level"] else ""
    worksheet["W47"] = data["section"].name if data["section"] else ""
    worksheet["R48"] = data["track_strand"]

    # ---------------- learning areas ----------------
    subjects = data["subjects"]
    if len(subjects) > SUBJECT_CAPACITY:
        warnings.append(
            f"This learner has {len(subjects)} learning areas but the SF9 sheet "
            f"has {SUBJECT_CAPACITY} rows — only the first {SUBJECT_CAPACITY} "
            "were written."
        )
    if not subjects:
        warnings.append(
            "No grades have been computed for this learner yet — the learning "
            "areas table was left blank."
        )

    for index, entry in enumerate(subjects[:SUBJECT_CAPACITY]):
        row = FIRST_SUBJECT_ROW + index
        worksheet[f"{SUBJECT_COL}{row}"] = entry["subject"].name

        periods = entry["periods"][:REQUIRED_PERIOD_COUNT]
        for term_index, column in enumerate(TERM_COLS):
            value = periods[term_index] if term_index < len(periods) else None
            worksheet[f"{column}{row}"] = value if value is not None else ""

        worksheet[f"{FINAL_COL}{row}"] = (
            entry["final_grade"] if entry["final_grade"] is not None else ""
        )
        worksheet[f"{REMARKS_COL}{row}"] = entry["remarks"] or ""

    incomplete = [
        entry["subject"].name
        for entry in subjects[:SUBJECT_CAPACITY]
        if entry["final_grade"] is None
    ]
    if incomplete:
        warnings.append(
            "These learning areas have no Final Grade yet (a term is still "
            "missing in the E-Class Record): " + ", ".join(incomplete) + "."
        )

    # ---------------- general average ----------------
    worksheet[f"{FINAL_COL}{GENERAL_AVERAGE_ROW}"] = (
        data["general_average"] if data["general_average"] is not None else ""
    )
    worksheet[f"{REMARKS_COL}{GENERAL_AVERAGE_ROW}"] = data["eligible_for_promotion_text"]

    # ---------------- attendance record ----------------
    attendance_rows = data["attendance_rows"]
    totals = data["attendance_totals"]
    for index, column in enumerate(ATTENDANCE_MONTH_COLS):
        if index >= len(attendance_rows):
            break
        month_row = attendance_rows[index]
        worksheet[f"{column}{CLASS_DAYS_ROW}"] = month_row["class_days"]
        worksheet[f"{column}{DAYS_PRESENT_ROW}"] = month_row["days_present"]
        worksheet[f"{column}{DAYS_ABSENT_ROW}"] = month_row["days_absent"]

    worksheet[f"{ATTENDANCE_TOTAL_COL}{CLASS_DAYS_ROW}"] = totals["class_days"]
    worksheet[f"{ATTENDANCE_TOTAL_COL}{DAYS_PRESENT_ROW}"] = totals["days_present"]
    worksheet[f"{ATTENDANCE_TOTAL_COL}{DAYS_ABSENT_ROW}"] = totals["days_absent"]

    if totals["class_days"] == 0:
        warnings.append(
            "No attendance has been recorded for this learner's section in this "
            "school year — the attendance record was left at zero."
        )

    # ---------------- transfer / approval blocks ----------------
    worksheet["AE67"] = options.get("admitted_to_grade") or ""
    worksheet["AG68"] = options.get("eligible_for_admission_to_grade") or ""
    worksheet["AK71"] = (options.get("adviser_name") or "").upper()
    worksheet["AK72"] = options.get("adviser_position") or ""
    principal_name = (options.get("principal_name") or "").upper()
    principal_position = options.get("principal_position") or ""
    worksheet["AD73"] = principal_name
    worksheet["AD74"] = principal_position
    worksheet["AD80"] = principal_name
    worksheet["AD81"] = principal_position

    return workbook, warnings
