"""
SF9 data source.

Single structured source of truth for the Learner's Permanent Report Card
(SF9), assembled from the computed Grade records (E-Class Record ->
transmuted Term Grades -> Final Grade) and the Attendance records.

SF9 is strictly dependent on computed grades: nothing here accepts a
manually supplied grade. The official SF9 Excel layout is a later phase;
this module is what both the existing PDF and that future export read.
"""

from __future__ import annotations

import calendar
import datetime

from classrecord.transmutation import PASSING_GRADE, descriptor, remarks
from attendance.models import Attendance
from enrollment.models import Enrollment
from grades.services import general_average_details, is_promoted, student_grades

# SF9_3Terms shows the school-year months June..March.
SF9_MONTH_SEQUENCE = [6, 7, 8, 9, 10, 11, 12, 1, 2, 3]


def _month_bounds(year, month):
    _, last_day = calendar.monthrange(year, month)
    return datetime.date(year, month, 1), datetime.date(year, month, last_day)


def _school_year_start(school_year):
    """
    First calendar year of the school year label (e.g. "2026-2027" -> 2026).
    Falls back to the current year when the label cannot be parsed.
    """
    text = str(getattr(school_year, "year", "") or "")
    digits = ""
    for character in text:
        if character.isdigit():
            digits += character
            if len(digits) == 4:
                break
        elif digits:
            break
    try:
        return int(digits)
    except ValueError:
        return datetime.date.today().year


def attendance_summary(student, school_year):
    """
    Per-month attendance for the SF9 attendance record block.

    Returns list of dicts (June..March):
        month_label, class_days, days_present, days_absent
    plus a totals dict. Class days = distinct dates with any attendance
    record for the learner's section in that month (Sundays excluded),
    matching how SF2 derives school days.
    """
    start_year = _school_year_start(school_year)

    enrollment = (
        Enrollment.objects.filter(student=student, school_year=school_year)
        .select_related("section")
        .first()
    )
    section_student_ids = []
    if enrollment is not None:
        section_student_ids = list(
            Enrollment.objects.filter(
                school_year=school_year, section=enrollment.section
            ).values_list("student_id", flat=True)
        )

    rows = []
    totals = {"class_days": 0, "days_present": 0, "days_absent": 0}

    for month in SF9_MONTH_SEQUENCE:
        year = start_year if month >= 6 else start_year + 1
        month_start, month_end = _month_bounds(year, month)

        class_days = set()
        if section_student_ids:
            class_days = {
                record_date
                for record_date in Attendance.objects.filter(
                    student_id__in=section_student_ids,
                    date__gte=month_start,
                    date__lte=month_end,
                ).values_list("date", flat=True)
                if record_date.weekday() != 6
            }

        own = Attendance.objects.filter(
            student=student, date__gte=month_start, date__lte=month_end
        )
        present = sum(
            1
            for record in own
            if record.status in ("Present", "Late") and record.date.weekday() != 6
        )
        absent = sum(
            1
            for record in own
            if record.status == "Absent" and record.date.weekday() != 6
        )

        rows.append(
            {
                "month": month,
                "month_label": datetime.date(year, month, 1).strftime("%b"),
                "class_days": len(class_days),
                "days_present": present,
                "days_absent": absent,
            }
        )
        totals["class_days"] += len(class_days)
        totals["days_present"] += present
        totals["days_absent"] += absent

    return rows, totals


def build_sf9_data(student, school_year):
    """
    Assemble the complete SF9 data set for one learner and school year.

    Returns a dict:
        student, school_year, enrollment, grade_level, section,
        track_strand, period_labels, subjects[], general_average,
        general_average_descriptor, general_average_remarks, promoted,
        eligible_for_promotion_text, attendance_rows, attendance_totals,
        passing_grade
    """
    enrollment = (
        Enrollment.objects.filter(student=student, school_year=school_year)
        .select_related("section", "grade_level")
        .first()
    )

    period_labels = [
        school_year.period_label(period)
        for period in range(1, school_year.period_count + 1)
    ]

    subjects = student_grades(student, school_year)
    average, average_descriptor, average_remarks = general_average_details(
        student, school_year
    )
    promoted = is_promoted(student, school_year)

    attendance_rows, attendance_totals = attendance_summary(student, school_year)

    return {
        "student": student,
        "school_year": school_year,
        "enrollment": enrollment,
        "grade_level": enrollment.grade_level if enrollment else None,
        "section": enrollment.section if enrollment else None,
        "track_strand": (
            enrollment.section.track_strand if enrollment and enrollment.section else ""
        ),
        "period_labels": period_labels,
        "subjects": subjects,
        "general_average": average,
        "general_average_descriptor": average_descriptor,
        "general_average_remarks": average_remarks,
        "promoted": promoted,
        "eligible_for_promotion_text": (
            "" if promoted is None else ("Promoted" if promoted else "Retained")
        ),
        "attendance_rows": attendance_rows,
        "attendance_totals": attendance_totals,
        "passing_grade": PASSING_GRADE,
        "descriptor_of": descriptor,
        "remarks_of": remarks,
    }
