"""
SF1-SHS export: fill a pristine copy of the bundled official template
(reports/templates_xlsx/SF1_SHS.xlsx) from database records.

The template's merges, borders, print settings and legend are never
touched — only value cells are written.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import openpyxl
from django.conf import settings

from enrollment.models import Enrollment

TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "templates_xlsx" / "SF1_SHS.xlsx"

SHEET_NAME = "SHSF-1"
BLOCK_CAPACITY = 40
MALE_FIRST_ROW = 11
FEMALE_FIRST_ROW = 52
TOTAL_MALE_CELL = "A51"
TOTAL_FEMALE_CELL = "A92"
TOTAL_COMBINED_CELL = "A93"

# Header value anchor cells (labels sit beside them in the template).
HEADER_CELLS = {
    "school_name": "F3",
    "school_id": "M3",
    "district": "U3",
    "division": "Z3",
    "region": "AF3",
    "semester": "F5",
    "school_year": "M5",
    "grade_level": "W5",
    "track_strand": "AC5",
    "section": "F7",
    "course": "P7",
}

LEARNER_CELLS = {
    "lrn": "A",
    "name": "C",
    "sex": "G",
    "birth_date": "H",
    "age": "J",
    "religious_affiliation": "L",
    "house_street": "M",
    "barangay": "N",
    "municipality": "R",
    "province": "U",
    "father_name": "W",
    "mother_maiden_name": "X",
    "guardian_name": "Z",
    "guardian_relationship": "AC",
    "contact_number": "AD",
    "remarks_code": "AE",
}


def _official_name(student):
    parts = [student.last_name or "", student.first_name or ""]
    name = f"{parts[0]}, {parts[1]}".strip(", ")
    if student.name_extension:
        name += f" {student.name_extension}"
    if student.middle_name:
        name += f", {student.middle_name}"
    return name.upper()


def _age_on(birth_date, as_of):
    if not birth_date:
        return ""
    years = as_of.year - birth_date.year - (
        (as_of.month, as_of.day) < (birth_date.month, birth_date.day)
    )
    return years


def _write_learner(worksheet, sheet_row, student, as_of):
    values = {
        "lrn": student.lrn,
        "name": _official_name(student),
        "sex": {"Male": "M", "Female": "F"}.get(student.gender, student.gender or ""),
        "birth_date": student.birth_date.strftime("%m/%d/%Y") if student.birth_date else "",
        "age": _age_on(student.birth_date, as_of),
        "religious_affiliation": student.religious_affiliation,
        "house_street": student.house_street,
        "barangay": student.barangay,
        "municipality": student.municipality,
        "province": student.province,
        "father_name": student.father_name,
        "mother_maiden_name": student.mother_maiden_name,
        "guardian_name": student.guardian_name,
        "guardian_relationship": student.guardian_relationship,
        "contact_number": student.contact_number,
        "remarks_code": student.remarks_code,
    }
    for field_name, col in LEARNER_CELLS.items():
        worksheet[f"{col}{sheet_row}"] = values[field_name]


def _clear_unused_placeholder(worksheet, first_row, used):
    """Blank the pre-printed counters on unused rows so the printed form
    doesn't show stray numbers below the roster."""
    for offset in range(used, BLOCK_CAPACITY):
        worksheet[f"A{first_row + offset}"] = None


def build_sf1_workbook(school_year, grade_level, section, semester_label):
    """
    Returns (openpyxl.Workbook, warnings: list[str]).

    Learners come from Enrollments of (school_year, section); males fill
    rows 11-50 and females rows 52-91, alphabetically, per the official
    layout. Block overflow beyond 40 is reported as a warning.
    """
    warnings = []
    workbook = openpyxl.load_workbook(TEMPLATE_PATH)
    worksheet = workbook[SHEET_NAME]

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
    }
    for field_name, cell in HEADER_CELLS.items():
        worksheet[cell] = header_values[field_name]

    enrollments = (
        Enrollment.objects.filter(school_year=school_year, section=section)
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    students = [e.student for e in enrollments]
    males = [s for s in students if s.gender == "Male"]
    females = [s for s in students if s.gender != "Male"]

    as_of = datetime.date.today()

    for block_label, group, first_row in (
        ("MALE", males, MALE_FIRST_ROW),
        ("FEMALE", females, FEMALE_FIRST_ROW),
    ):
        if len(group) > BLOCK_CAPACITY:
            warnings.append(
                f"{block_label} learners exceed the form capacity "
                f"({len(group)} > {BLOCK_CAPACITY}) — only the first "
                f"{BLOCK_CAPACITY} were written. Split the section across "
                "additional SF1 sheets."
            )
        for index, student in enumerate(group[:BLOCK_CAPACITY]):
            _write_learner(worksheet, first_row + index, student, as_of)
        _clear_unused_placeholder(worksheet, first_row, min(len(group), BLOCK_CAPACITY))

    worksheet[TOTAL_MALE_CELL] = len(males)
    worksheet[TOTAL_FEMALE_CELL] = len(females)
    worksheet[TOTAL_COMBINED_CELL] = len(students)

    return workbook, warnings
