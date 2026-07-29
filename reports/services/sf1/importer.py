"""
SF1 import classification and database application.

classify(...)      read-only; tags every parsed row with the six-state
                   vocabulary (created/updated/no_change + already_enrolled/
                   conflict) and computes the field-level diff for updates.
apply_import(...)  the only writer; runs inside one atomic transaction.

Idempotency contract: LRN is the sole student identity; Enrollment identity
is (student, school_year) via get_or_create backed by the DB unique
constraint. Re-uploading the same file creates nothing the second time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from enrollment.models import Enrollment
from students.models import Student

from ..base import (
    ALREADY_ENROLLED,
    CONFLICT,
    CREATED,
    NO_CHANGE,
    UPDATED,
    diff_fields,
)

# Field -> preview label for the diff engine. These are exactly the 16
# SF1-mapped Student fields (4 original + 12 Category 1).
DIFF_FIELD_LABELS = {
    "last_name": "Last Name",
    "first_name": "First Name",
    "name_extension": "Name Extension",
    "middle_name": "Middle Name",
    "gender": "Sex",
    "birth_date": "Birthdate",
    "religious_affiliation": "Religious Affiliation",
    "house_street": "House No./Street/Sitio/Purok",
    "barangay": "Barangay",
    "municipality": "Municipality/City",
    "province": "Province",
    "father_name": "Father's Name",
    "mother_maiden_name": "Mother's Maiden Name",
    "guardian_name": "Guardian Name",
    "guardian_relationship": "Guardian Relationship",
    "contact_number": "Contact Number",
    "remarks_code": "Remarks",
}


@dataclass
class ImportSummary:
    created: int = 0
    updated: int = 0
    no_change: int = 0
    enrolled: int = 0
    already_enrolled: int = 0
    conflicts: int = 0
    skipped_errors: int = 0
    conflict_details: list = field(default_factory=list)


def classify(parse_result, school_year, grade_level, section):
    """
    Read-only classification of every valid parsed row against the DB.

    Sets row.status (created/updated/no_change), row.enrollment_status
    (''/already_enrolled/conflict), row.diff and row.existing_pk.
    """
    lrns = [r.data["lrn"] for r in parse_result.valid_rows]
    existing_students = {
        s.lrn: s for s in Student.objects.filter(lrn__in=lrns)
    }
    enrollments = {
        e.student_id: e
        for e in Enrollment.objects.filter(
            student__lrn__in=lrns, school_year=school_year
        ).select_related("section", "grade_level")
    }

    for row in parse_result.valid_rows:
        student = existing_students.get(row.data["lrn"])

        if student is None:
            row.status = CREATED
            row.diff = []
            row.existing_pk = None
        else:
            row.existing_pk = student.pk
            row.diff = diff_fields(student, row.data, DIFF_FIELD_LABELS)
            row.status = UPDATED if row.diff else NO_CHANGE

            enrollment = enrollments.get(student.pk)
            if enrollment is not None:
                same_place = (
                    enrollment.section_id == section.pk
                    and enrollment.grade_level_id == grade_level.pk
                )
                row.enrollment_status = ALREADY_ENROLLED if same_place else CONFLICT

    return parse_result


def apply_import(parse_result, school_year, grade_level, section, semester=None):
    """
    Apply a classified parse result inside one atomic transaction.

    Update rule: only non-empty incoming values overwrite; empty cells in
    the file never erase existing data. CONFLICT rows get their student
    fields refreshed but their existing enrollment is left untouched.
    ``semester`` (optional, "1"/"2") is recorded on enrollments created by
    this import, and fills the field on existing same-section enrollments
    that don't have it yet (never overwrites a different value).
    """
    summary = ImportSummary()
    summary.skipped_errors = len(parse_result.error_rows)

    with transaction.atomic():
        for row in parse_result.valid_rows:
            if row.status == CREATED:
                student = Student.objects.create(**row.data)
                summary.created += 1
            else:
                student = Student.objects.select_for_update().get(pk=row.existing_pk)
                # Recompute the diff inside the transaction — the DB may
                # have changed since the preview.
                row.diff = diff_fields(student, row.data, DIFF_FIELD_LABELS)
                if row.diff:
                    for field_name in DIFF_FIELD_LABELS:
                        incoming = row.data.get(field_name)
                        if incoming not in (None, ""):
                            setattr(student, field_name, incoming)
                    student.save()
                    row.status = UPDATED
                    summary.updated += 1
                else:
                    row.status = NO_CHANGE
                    summary.no_change += 1

            if row.enrollment_status == CONFLICT:
                summary.conflicts += 1
                existing = Enrollment.objects.filter(
                    student=student, school_year=school_year
                ).select_related("section", "grade_level").first()
                if existing:
                    summary.conflict_details.append(
                        f"Row {row.sheet_row}: {student} is already enrolled in "
                        f"{existing.grade_level} - {existing.section.name} for "
                        f"{school_year} — enrollment left unchanged."
                    )
                continue

            enrollment, enrolled_now = Enrollment.objects.get_or_create(
                student=student,
                school_year=school_year,
                defaults={
                    "grade_level": grade_level,
                    "section": section,
                    "semester": semester,
                },
            )
            if enrolled_now:
                summary.enrolled += 1
            else:
                summary.already_enrolled += 1
                if semester and not enrollment.semester:
                    enrollment.semester = semester
                    enrollment.save(update_fields=["semester"])

    return summary
