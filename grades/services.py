"""
General Average and subject Final Grade helpers (DepEd Order No. 8, s. 2015).

Pure read-only computation over existing Grade records — no schema change.
Used by the SF9 data source and, later, by ranking/awards.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from classrecord.transmutation import PASSING_GRADE, descriptor, remarks, round_whole
from .models import Grade


def subject_final_grade(grade):
    """
    Whole-number Final Grade for one Grade row (half-up), or None when the
    applicable periods are not all present yet.
    """
    if grade is None or grade.final_grade is None:
        return None
    return round_whole(grade.final_grade)


def _subject_semester_map(student, school_year, section=None):
    """
    {subject_id: semester} derived from SubjectAssignment for the given
    school year (and the learner's section when known). Only assignments
    that have a semester set contribute; others are omitted.
    """
    from academics.models import SubjectAssignment

    assignments = SubjectAssignment.objects.filter(
        school_year=school_year, semester__isnull=False
    )
    if section is not None:
        assignments = assignments.filter(section=section)

    mapping = {}
    for assignment in assignments.values("subject_id", "semester"):
        mapping.setdefault(assignment["subject_id"], assignment["semester"])
    return mapping


def student_grades(student, school_year, semester=None, section=None):
    """
    Ordered list of dicts, one per subject with a Grade record:
        subject, periods (list of whole-number term grades, per grading
        system), final_grade (whole), descriptor, remarks, semester

    When ``semester`` is given ("1"/"2"), only subjects whose
    SubjectAssignment.semester matches are returned. Subjects with no
    semester on their assignment are treated as unassigned:
      * semester=None  -> all subjects (unchanged, backward compatible)
      * semester="1"/"2" -> only that semester's subjects
    """
    semester_map = _subject_semester_map(student, school_year, section)

    rows = []
    grades = (
        Grade.objects.filter(student=student, school_year=school_year)
        .select_related("subject", "school_year")
        .order_by("subject__code", "subject__name")
    )
    for grade in grades:
        subject_semester = semester_map.get(grade.subject_id)
        if semester is not None and subject_semester != semester:
            continue
        final = subject_final_grade(grade)
        rows.append(
            {
                "subject": grade.subject,
                "periods": [round_whole(value) for value in grade.period_values()],
                "final_grade": final,
                "descriptor": descriptor(final),
                "remarks": remarks(final),
                "semester": subject_semester,
            }
        )
    return rows


def general_average(student, school_year):
    """
    General Average = mean of the subject Final Grades for the school year,
    rounded half-up to a whole number.

    Returns None when no subject has a complete Final Grade yet (a subject
    still missing a period is excluded from the average).
    """
    finals = [
        grade.final_grade
        for grade in Grade.objects.filter(student=student, school_year=school_year)
        if grade.final_grade is not None
    ]
    if not finals:
        return None

    total = sum((Decimal(str(value)) for value in finals), Decimal("0"))
    average = total / Decimal(len(finals))
    return int(average.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def general_average_details(student, school_year):
    """(general_average, descriptor, remarks) — None-safe."""
    average = general_average(student, school_year)
    return average, descriptor(average), remarks(average)


def is_promoted(student, school_year):
    """
    True when every subject with a Final Grade meets the passing mark.
    None when there are no computed final grades yet.
    """
    finals = [
        grade.final_grade
        for grade in Grade.objects.filter(student=student, school_year=school_year)
        if grade.final_grade is not None
    ]
    if not finals:
        return None
    return all(Decimal(str(value)) >= PASSING_GRADE for value in finals)


# ---------------------------------------------------------------------------
# Ranking and Awards services (additive — no schema change)
# ---------------------------------------------------------------------------

# DepEd Awards thresholds (DOCX Module 10)
AWARD_THRESHOLDS = [
    (98, "With Highest Honors"),
    (95, "With High Honors"),
    (90, "With Honors"),
]


def _award_for(avg):
    """
    Return the award label for a General Average, or '' if none.

    Thresholds from DOCX Module 10 — no other condition is documented:
      98-100 → With Highest Honors
      95-97  → With High Honors
      90-94  → With Honors
    """
    if avg is None:
        return ""
    for cutoff, label in AWARD_THRESHOLDS:
        if avg >= cutoff:
            return label
    return ""


def class_ranking(school_year, section=None):
    """
    Return an ordered list of dicts for all enrolled students in the given
    school year (and optional section), ranked by General Average descending.

    Uses the existing ``general_average()`` service exactly as-is.

    Each dict:
        rank, student, general_average, descriptor, remarks, award, promoted
    Students with no computed General Average appear last (avg=None).
    """
    from enrollment.models import Enrollment

    enrollments = Enrollment.objects.filter(
        school_year=school_year
    ).select_related("student", "section", "grade_level")
    if section is not None:
        enrollments = enrollments.filter(section=section)

    rows = []
    for enr in enrollments:
        avg = general_average(enr.student, school_year)
        _, desc, rem = general_average_details(enr.student, school_year)
        rows.append({
            "student":         enr.student,
            "section":         enr.section,
            "general_average": avg,
            "descriptor":      desc,
            "remarks":         rem,
            "award":           _award_for(avg),
            "promoted":        is_promoted(enr.student, school_year),
        })

    # Sort: students with an average first (descending), then those without
    rows.sort(key=lambda r: (r["general_average"] is None, -(r["general_average"] or 0)))

    # Assign ranks — ties share the same rank number (standard competition ranking)
    rank = 0
    prev_avg = object()  # sentinel
    for index, row in enumerate(rows):
        if row["general_average"] != prev_avg:
            rank = index + 1
            prev_avg = row["general_average"]
        row["rank"] = rank if row["general_average"] is not None else "—"

    return rows


def subject_ranking(school_year, subject, section=None):
    """
    Return students ranked by a single subject's Final Grade, descending.

    Each dict: rank, student, section, final_grade, descriptor, remarks
    """
    from enrollment.models import Enrollment

    enrolled_ids = Enrollment.objects.filter(
        school_year=school_year
    )
    if section is not None:
        enrolled_ids = enrolled_ids.filter(section=section)
    enrolled_ids = set(enrolled_ids.values_list("student_id", flat=True))

    grade_rows = (
        Grade.objects.filter(
            school_year=school_year,
            subject=subject,
            student_id__in=enrolled_ids,
            final_grade__isnull=False,
        )
        .select_related("student")
        .order_by("-final_grade")
    )

    # Map student → section for display
    section_map = {
        enr["student_id"]: enr["section__name"]
        for enr in Enrollment.objects.filter(
            school_year=school_year, student_id__in=enrolled_ids
        ).values("student_id", "section__name")
    }

    rows = []
    rank = 0
    prev_fg = object()
    for index, g in enumerate(grade_rows):
        fg = int(g.final_grade)
        if fg != prev_fg:
            rank = index + 1
            prev_fg = fg
        rows.append({
            "rank":        rank,
            "student":     g.student,
            "section":     section_map.get(g.student_id, "—"),
            "final_grade": fg,
            "descriptor":  descriptor(fg),
            "remarks":     remarks(fg),
        })

    return rows


def awards_list(school_year, section=None):
    """
    Return three groups of award recipients for the school year.
    Only students who are promoted (passed every subject) qualify.

    Returns:
        {
            "With Highest Honors": [...],   # GA 98-100
            "With High Honors":    [...],   # GA 95-97
            "With Honors":         [...],   # GA 90-94
        }
    Each entry: student, section, general_average
    """
    ranked = class_ranking(school_year, section)
    groups = {label: [] for _, label in AWARD_THRESHOLDS}

    for row in ranked:
        if row["award"]:
            groups[row["award"]].append({
                "student":         row["student"],
                "section":         row["section"],
                "general_average": row["general_average"],
            })

    return groups
