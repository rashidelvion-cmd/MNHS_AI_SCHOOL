"""
SF2-SHS export: fill a pristine copy of the bundled official template
(reports/templates_xlsx/SF2_SHS.xlsx) from Attendance and Enrollment
records for one section and one reporting month.

Marking codes follow the printed legend: blank = Present, "x" = Absent.
The paper form's half-shaded cell for Tardy cannot be reproduced as text,
so tardiness is written as "/" (noted to the user as a warning once per
export). The TARDY totals column carries the exact counts regardless.

Documented approximations (no schema exists for these, per the approved
plan): "Enrolment as of 1st Friday" and "Late Enrolment during the month"
derive from Enrollment.date_enrolled (the date the enrollment record was
created); "Registered as of end of month" excludes learners whose
Student.remarks_code contains T/O or NLS.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import openpyxl
from django.conf import settings

from attendance.models import Attendance
from enrollment.models import Enrollment

from .calendar_map import DATE_ROW, map_dates_to_columns

TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "templates_xlsx" / "SF2_SHS.xlsx"

SHEET_NAME = "SHSF-2"

MALE_FIRST_ROW = 12
MALE_CAPACITY = 17          # rows 12..28
MALE_TOTAL_ROW = 29
FEMALE_FIRST_ROW = 30
FEMALE_CAPACITY = 27        # rows 30..56
FEMALE_TOTAL_ROW = 57
COMBINED_TOTAL_ROW = 58

NAME_COL = "C"
NUMBER_COL = "A"
ABSENT_TOTAL_COL = "AR"
TARDY_TOTAL_COL = "AT"
REMARKS_COL = "AV"

HEADER_CELLS = {
    "school_name": "F3",       # label A3:E3  -> value F3:P3
    "school_id": "V3",         # label R3:U3  -> value V3:AA3
    "district": "AF3",         # label AC3:AE3 -> value AF3:AL3
    "division": "AR3",         # label AM3:AQ3 -> value AR3:AV3
    "region": "AX3",           # label AW3     -> value AX3:AY3
    "semester": "F5",          # label E5      -> value F5:P5
    "school_year": "V5",       # label Q5:U5   -> value V5:AA5
    "grade_level": "AH5",      # label AC5:AG5 -> value AH5:AJ5
    "track_strand": "AV5",     # label AN5:AU5 -> value AV5:AY5
    "section": "F7",           # label E7      -> value F7:N7
    "course": "W7",            # label O7:V7   -> value W7:AO7
    "month": "AV7",            # label AS7:AU7 -> value AV7:AY7
}

# Summary box: label rows on the right side; values in columns AW/AX/AY
# (Male / Female / Total).
SUMMARY_ROWS = {
    "enrolment_first_friday": 62,
    "late_enrolment": 63,
    "registered_end_of_month": 64,
    "percentage_enrolment": 65,
    "average_daily_attendance": 66,
    "percentage_attendance": 67,
    "absent_5_consecutive": 68,
    "nls": 70,
    "transferred_out": 71,
    "transferred_in": 72,
    "shifting_out": 73,
    "shifting_in": 74,
}
SUMMARY_VALUE_COLS = ("AW", "AX", "AY")
# Row-60 label cells carry their own printed text; values are appended
# into the label cell to preserve the template ("Month: June 2026").
SUMMARY_MONTH_LABEL_CELL = "AR60"
DAYS_OF_CLASSES_LABEL_CELL = "AU60"

ABSENT_MARK = "x"
TARDY_MARK = "/"


def _official_name(student):
    name = f"{student.last_name or ''}, {student.first_name or ''}".strip(", ")
    if student.name_extension:
        name += f" {student.name_extension}"
    if student.middle_name:
        name += f", {student.middle_name}"
    return name.upper()


def _has_code(student, *codes):
    remarks = (student.remarks_code or "").upper()
    return any(code in remarks for code in codes)


def _first_friday(year, month):
    date = datetime.date(year, month, 1)
    while date.weekday() != 4:  # Friday
        date += datetime.timedelta(days=1)
    return date


def _consecutive_absent_5(statuses_by_date, school_days):
    """True if the learner was Absent on 5+ consecutive school days."""
    run = 0
    for day in school_days:
        if statuses_by_date.get(day) == "Absent":
            run += 1
            if run >= 5:
                return True
        else:
            run = 0
    return False


def build_sf2_workbook(school_year, grade_level, section, semester_label, year, month):
    """
    Returns (openpyxl.Workbook, warnings: list[str]).

    School days = dates in the month having at least one Attendance record
    for the section's enrolled learners (Mon-Sat).
    """
    warnings = []
    workbook = openpyxl.load_workbook(TEMPLATE_PATH)
    worksheet = workbook[SHEET_NAME]

    month_name = datetime.date(year, month, 1).strftime("%B %Y")

    header_values = {
        "school_name": settings.SCHOOL_NAME,
        "school_id": getattr(settings, "SCHOOL_ID", ""),
        "district": getattr(settings, "SCHOOL_DISTRICT", ""),
        "division": getattr(settings, "SCHOOL_DIVISION", ""),
        "region": getattr(settings, "SCHOOL_REGION", ""),
        "semester": semester_label,
        "school_year": str(school_year),
        "grade_level": grade_level.name,
        "track_strand": section.track_strand,
        "section": section.name,
        "course": section.course,
        "month": month_name,
    }
    for field_name, cell in HEADER_CELLS.items():
        worksheet[cell] = header_values[field_name]

    enrollments = (
        Enrollment.objects.filter(school_year=school_year, section=section)
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    students = [e.student for e in enrollments]
    enrollment_by_student = {e.student_id: e for e in enrollments}
    males = [s for s in students if s.gender == "Male"]
    females = [s for s in students if s.gender != "Male"]

    month_start = datetime.date(year, month, 1)
    next_month = (month_start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    month_end = next_month - datetime.timedelta(days=1)

    records = Attendance.objects.filter(
        student__in=students, date__gte=month_start, date__lte=month_end
    )
    by_student = {}
    school_day_set = set()
    for record in records:
        if record.date.weekday() == 6:
            continue  # Sundays never appear on the form
        by_student.setdefault(record.student_id, {})[record.date] = record.status
        school_day_set.add(record.date)

    school_days = sorted(school_day_set)
    if not school_days:
        warnings.append(
            f"No attendance records exist for {section.name} in {month_name} — "
            "the day grid and totals are empty."
        )

    column_map, overflow = map_dates_to_columns(school_days)
    if overflow:
        days = ", ".join(str(d.day) for d in overflow)
        warnings.append(
            f"Days {days} fall on a sixth calendar week and do not fit the "
            "form's five week-columns — they were left off the grid (their "
            "absences still count in the totals)."
        )

    tardy_used = False
    for date, column in column_map.items():
        worksheet[f"{column}{DATE_ROW}"] = date.day

    per_day_counts = {
        "M": {d: 0 for d in school_days},
        "F": {d: 0 for d in school_days},
    }
    summary_counts = {key: {"M": 0, "F": 0} for key in SUMMARY_ROWS}
    total_daily_attendance = {"M": 0, "F": 0}

    def write_block(group, first_row, capacity, block_key, block_label):
        nonlocal tardy_used
        if len(group) > capacity:
            warnings.append(
                f"{block_label} learners exceed the SF2 capacity "
                f"({len(group)} > {capacity}) — only the first {capacity} "
                "were written. Split the section across additional sheets."
            )
        for index, student in enumerate(group[:capacity]):
            row_number = first_row + index
            worksheet[f"{NUMBER_COL}{row_number}"] = index + 1
            worksheet[f"{NAME_COL}{row_number}"] = _official_name(student)

            statuses = by_student.get(student.pk, {})
            absent = 0
            tardy = 0
            for date in school_days:
                status = statuses.get(date)
                column = column_map.get(date)
                if status == "Absent":
                    absent += 1
                    if column:
                        worksheet[f"{column}{row_number}"] = ABSENT_MARK
                else:
                    # Present or Late count as attendance for the day.
                    if status is not None:
                        per_day_counts[block_key][date] += 1
                        total_daily_attendance[block_key] += 1
                    if status == "Late":
                        tardy += 1
                        tardy_used = True
                        if column:
                            worksheet[f"{column}{row_number}"] = TARDY_MARK

            worksheet[f"{ABSENT_TOTAL_COL}{row_number}"] = absent
            worksheet[f"{TARDY_TOTAL_COL}{row_number}"] = tardy
            if student.remarks_code:
                worksheet[f"{REMARKS_COL}{row_number}"] = student.remarks_code

            if _consecutive_absent_5(statuses, school_days):
                summary_counts["absent_5_consecutive"][block_key] += 1

        # clear unused pre-printed counters
        for offset in range(min(len(group), capacity), capacity):
            worksheet[f"{NUMBER_COL}{first_row + offset}"] = None

    write_block(males, MALE_FIRST_ROW, MALE_CAPACITY, "M", "MALE")
    write_block(females, FEMALE_FIRST_ROW, FEMALE_CAPACITY, "F", "FEMALE")

    if tardy_used:
        warnings.append(
            'Tardy days are marked "/" (the paper form\'s half-shaded cell '
            "cannot be reproduced in text). Exact counts are in the TARDY column."
        )

    for date, column in column_map.items():
        worksheet[f"{column}{MALE_TOTAL_ROW}"] = per_day_counts["M"][date]
        worksheet[f"{column}{FEMALE_TOTAL_ROW}"] = per_day_counts["F"][date]
        worksheet[f"{column}{COMBINED_TOTAL_ROW}"] = (
            per_day_counts["M"][date] + per_day_counts["F"][date]
        )

    # ---------------- Summary box ----------------
    first_friday = _first_friday(year, month if month else 1)
    for student in students:
        block_key = "M" if student.gender == "Male" else "F"
        enrollment = enrollment_by_student[student.pk]
        enrolled_on = enrollment.date_enrolled

        if enrolled_on is None or enrolled_on <= first_friday:
            summary_counts["enrolment_first_friday"][block_key] += 1
        elif month_start <= enrolled_on <= month_end:
            summary_counts["late_enrolment"][block_key] += 1
        else:
            summary_counts["enrolment_first_friday"][block_key] += 1

        dropped = _has_code(student, "T/O", "NLS")
        if not dropped:
            summary_counts["registered_end_of_month"][block_key] += 1
        if _has_code(student, "NLS"):
            summary_counts["nls"][block_key] += 1
        if _has_code(student, "T/O"):
            summary_counts["transferred_out"][block_key] += 1
        if _has_code(student, "T/I"):
            summary_counts["transferred_in"][block_key] += 1

    day_count = len(school_days)
    worksheet[SUMMARY_MONTH_LABEL_CELL] = f"Month: {month_name}"
    worksheet[DAYS_OF_CLASSES_LABEL_CELL] = f"No. of Days of Classes: {day_count}"

    def registered(block_key):
        return summary_counts["registered_end_of_month"][block_key]

    for block_index, block_key in enumerate(("M", "F")):
        enrolled_ff = summary_counts["enrolment_first_friday"][block_key]
        reg = registered(block_key)
        if enrolled_ff:
            summary_counts["percentage_enrolment"][block_key] = round(
                reg / enrolled_ff * 100, 1
            )
        if day_count:
            ada = round(total_daily_attendance[block_key] / day_count, 1)
            summary_counts["average_daily_attendance"][block_key] = ada
            if reg:
                summary_counts["percentage_attendance"][block_key] = round(
                    ada / reg * 100, 1
                )

    for key, row_number in SUMMARY_ROWS.items():
        male_value = summary_counts[key]["M"]
        female_value = summary_counts[key]["F"]
        if key in ("percentage_enrolment", "percentage_attendance", "average_daily_attendance"):
            total_value = ""
            if male_value or female_value:
                # Recompute totals from combined figures for correctness.
                if key == "average_daily_attendance" and len(school_days):
                    total_value = round(
                        (total_daily_attendance["M"] + total_daily_attendance["F"])
                        / len(school_days),
                        1,
                    )
                elif key == "percentage_enrolment":
                    ff = (
                        summary_counts["enrolment_first_friday"]["M"]
                        + summary_counts["enrolment_first_friday"]["F"]
                    )
                    reg_total = registered("M") + registered("F")
                    total_value = round(reg_total / ff * 100, 1) if ff else ""
                elif key == "percentage_attendance":
                    reg_total = registered("M") + registered("F")
                    if reg_total and len(school_days):
                        ada_total = (
                            total_daily_attendance["M"] + total_daily_attendance["F"]
                        ) / len(school_days)
                        total_value = round(ada_total / reg_total * 100, 1)
        else:
            total_value = male_value + female_value

        worksheet[f"{SUMMARY_VALUE_COLS[0]}{row_number}"] = male_value
        worksheet[f"{SUMMARY_VALUE_COLS[1]}{row_number}"] = female_value
        worksheet[f"{SUMMARY_VALUE_COLS[2]}{row_number}"] = total_value

    return workbook, warnings
