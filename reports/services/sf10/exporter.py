"""
Official SF10-SHS (Senior High School Learner's Permanent Record) export.

Fills a pristine copy of the bundled official template
(reports/templates_xlsx/SF10_SHS.xlsx) from the existing Student,
Enrollment and Grade data, reusing the SF9 data source for the computed
grades. No grade is computed here.

=====================================================================
3-TERM COMPATIBILITY (documented limitation)
=====================================================================
The official SF10-SHS records each semester as two quarters (Q1/Q2 for
the first semester, Q3/Q4 for the second) and derives everything else
from them with live worksheet formulas.

This school uses the 3-Term grading system, which the client has
confirmed will not change. Three terms cannot be written into two
quarter columns without misstating them, so:

  * Q1..Q4 columns (R/S in the semester blocks and Q..T in the summary)
    are LEFT BLANK. They are never populated with term data.
  * The semestral grade column ("1ST/2ND SEMESTRAL GRADE - GEN. AVE.",
    column T) receives the subject's computed Final Grade. Under the
    3-Term system a school year plus Enrollment.semester represents one
    semester, so the subject's Final Grade (mean of its three terms) IS
    that subject's semestral grade. This mapping is exact.
  * The summary "FINAL GRADE / GEN. AVE." column (W) receives the same
    computed Final Grade as a value, because the template derives that
    cell from the quarter columns which stay blank under 3-Term.

Formula preservation:
  * Core subject rows have empty T/U cells in the template, so writing
    them is lossless.
  * Elective rows and the summary rows carry formulas that depend on the
    (blank) quarter cells and would therefore resolve to "" anyway;
    where a computed value must appear, the value is written and the
    replacement is reported in the returned warnings.
  * Every other formula is untouched, including the General Average
    (FRONT!W123, BACK!W89) and the SHS General Average (BACK!W93), which
    recompute from the values written here.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import openpyxl
from openpyxl.worksheet.formula import ArrayFormula
from django.conf import settings

from enrollment.models import Enrollment

from ..sf9.data import build_sf9_data

TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "templates_xlsx" / "SF10_SHS.xlsx"
)

PASSING_GRADE = 75

# --------------------------------------------------------------------------
# Verified template geometry
# --------------------------------------------------------------------------

FRONT = {
    "sheet": "FRONT",
    "grade_level_digit": "11",
    "learner": {
        "last_name": "C7",
        "first_name": "K7",
        "middle_name": "S7",
        "name_extension": "Y7",
        "lrn": "C8",
        "birth_date": "K8",
        "gender": "P8",
        "admission_date": "W8",
    },
    "blocks": {
        "1": {
            "school": "C22", "school_id": "N22", "grade_level": "S22",
            "section": "W22", "track": "C23", "school_year": "S23", "semester": "W23",
            "first_row": 28, "last_row": 41, "last_core_row": 34,
            "summary_offset": 76,
        },
        "2": {
            "school": "C61", "school_id": "N61", "grade_level": "S61",
            "section": "W61", "track": "C62", "school_year": "S62", "semester": "W62",
            "first_row": 67, "last_row": 80, "last_core_row": 73,
            "summary_offset": 37,
        },
    },
    "summary": {"first_row": 104, "last_row": 122},
}

BACK = {
    "sheet": "BACK",
    "grade_level_digit": "12",
    "learner": None,          # the learner block lives on FRONT only
    "blocks": {
        "1": {
            "school": "C3", "school_id": "N3", "grade_level": "S3",
            "section": "W3", "track": "C4", "school_year": "S4", "semester": "W4",
            "first_row": 9, "last_row": 18, "last_core_row": 8,   # no pre-printed cores
            "summary_offset": 68,
        },
        "2": {
            "school": "C38", "school_id": "N38", "grade_level": "S38",
            "section": "W38", "track": "C39", "school_year": "S39", "semester": "W39",
            "first_row": 44, "last_row": 53, "last_core_row": 43,
            "summary_offset": 33,
        },
    },
    "summary": {"first_row": 77, "last_row": 88},
}

SUBJECT_COL = "D"
TRACK_TYPE_COL = "B"
SEMESTRAL_GRADE_COL = "T"
ACTION_TAKEN_COL = "U"
SUMMARY_FINAL_COL = "W"

SEMESTER_WORD = {"1": "FIRST", "2": "SECOND"}


class SF10ExportError(Exception):
    """Raised when the learner/grade level cannot produce a valid SF10."""


def _normalize(text):
    return " ".join(str(text or "").split()).strip().lower()


def _is_formula(value):
    """True for both plain '=' formulas and shared/array formulas."""
    if isinstance(value, ArrayFormula):
        return True
    return isinstance(value, str) and value.startswith("=")


def _has_written_text(value):
    """A pre-printed literal name (formula placeholders don't count)."""
    return bool(value) and not _is_formula(value)


def _grade_level_digit(grade_level):
    digits = "".join(ch for ch in str(grade_level.name) if ch.isdigit())
    return digits


def _sheet_config(grade_level):
    digit = _grade_level_digit(grade_level)
    if digit == "11":
        return FRONT
    if digit == "12":
        return BACK
    raise SF10ExportError(
        f"SF10-SHS covers Grade 11 (front page) and Grade 12 (back page) only — "
        f"'{grade_level.name}' cannot be exported with this form."
    )


def _core_rows(worksheet, block):
    """{normalized pre-printed subject name: row} for this block's core rows."""
    rows = {}
    for row in range(block["first_row"], block["last_core_row"] + 1):
        name = worksheet[f"{SUBJECT_COL}{row}"].value
        if _has_written_text(name):
            rows[_normalize(name)] = row
    return rows


def _enrollments_for(student, grade_level):
    return list(
        Enrollment.objects.filter(student=student, grade_level=grade_level)
        .select_related("school_year", "section")
        .order_by("semester", "school_year__year")
    )


def _build_semester_plan(enrollments, grade_level):
    """
    Decide which enrollment drives each SF10 semester block.

    Two cases are supported, both 3-Term and additive:

      * Separate enrollments per semester (Enrollment.semester = "1"/"2")
        -> each drives its own block.
      * A single enrollment whose SchoolYear carries both semesters'
        SubjectAssignment.semester values -> that one enrollment drives
        BOTH blocks; subjects are split later by SubjectAssignment.semester.

    Returns {"1": enrollment_or_None, "2": enrollment_or_None}.
    """
    from academics.models import SubjectAssignment

    plan = {"1": None, "2": None}

    # First, honour explicit per-semester enrollments.
    for enrollment in enrollments:
        if enrollment.semester in ("1", "2") and plan[enrollment.semester] is None:
            plan[enrollment.semester] = enrollment

    # Then, for any still-empty block, see if an enrollment's school year
    # has subject assignments for that semester (single-SchoolYear case).
    for enrollment in enrollments:
        year_semesters = set(
            SubjectAssignment.objects.filter(
                school_year=enrollment.school_year,
                section=enrollment.section,
                semester__isnull=False,
            ).values_list("semester", flat=True)
        )
        for semester in ("1", "2"):
            if plan[semester] is None and semester in year_semesters:
                plan[semester] = enrollment

    # Fallback: an enrollment with no semester and no assignment semesters
    # still fills the first block (backward-compatible behaviour).
    if plan["1"] is None and plan["2"] is None and enrollments:
        plan["1"] = enrollments[0]

    return plan


def _resolve_subject_semesters(school_year, section, graded_subject_ids, fallback_semester="1"):
    """
    Classify every graded subject into exactly one SF10 semester bucket.

    ``fallback_semester`` is the block a subject falls back to when it has
    no usable same-section semester (unassigned, section-mismatch, or
    legacy all-NULL). It defaults to "1" (First Semester) so single-
    SchoolYear behavior is unchanged; in the two-enrollment case the caller
    passes the semester of the block that this enrollment drives, so a NULL
    subject lands in its own block rather than always in First Semester.

    Returns (resolution, notes) where:
      resolution = {subject_id: "1" | "2"}   — the block each subject goes to
      notes = {
        "unassigned":       [subject_id, ...],   # no semester / no assignment
        "section_mismatch": {subject_id: other_section_name, ...},
        "conflict":         {subject_id: [sem, sem], ...},
        "cross_section_conflict": {subject_id: (own_sem, section, other_sem)},
        "legacy_all_null":  bool,                 # no semester anywhere in year
      }

    Rules (approved):
      * same-section assignment with a semester -> that semester
      * conflicting same-section semesters      -> lowest, flagged conflict
      * only wrong-section assignments          -> fallback, flagged mismatch
      * no semester anywhere in the year        -> all fallback, legacy flag
      * a graded subject with no assignment      -> fallback, unassigned
    No subject is ever omitted; each maps to exactly one block.
    """
    from academics.models import SubjectAssignment

    assignments = list(
        SubjectAssignment.objects.filter(school_year=school_year)
        .order_by("semester", "id")
        .values("subject_id", "semester", "section_id")
    )

    year_has_any_semester = any(a["semester"] for a in assignments)

    # same-section semesters per subject, and wrong-section fallbacks
    same_section = {}   # subject_id -> [semesters...]
    other_section = {}  # subject_id -> other_section_id (first seen)
    other_section_sem = {}  # subject_id -> semester on the wrong-section assignment
    section_names = {}
    for a in assignments:
        sid = a["subject_id"]
        if a["section_id"] == (section.pk if section else None):
            if a["semester"]:
                same_section.setdefault(sid, []).append(a["semester"])
        else:
            if a["semester"] and sid not in other_section:
                other_section[sid] = a["section_id"]
                other_section_sem[sid] = a["semester"]

    if other_section:
        for sec_obj in _sections_by_ids(set(other_section.values())):
            section_names[sec_obj.pk] = sec_obj.name

    resolution = {}
    notes = {
        "unassigned": [],
        "section_mismatch": {},
        "conflict": {},
        "cross_section_conflict": {},   # subject_id -> (own_sem, other_section, other_sem)
        "legacy_all_null": not year_has_any_semester,
    }

    for subject_id in graded_subject_ids:
        semesters = same_section.get(subject_id, [])
        distinct = sorted(set(semesters))

        if len(distinct) == 1:
            resolution[subject_id] = distinct[0]
            # M-2: a valid same-section semester is authoritative; if a
            # wrong-section assignment disagrees, surface it (do not let it
            # override the correct-section value).
            if subject_id in other_section_sem and other_section_sem[subject_id] != distinct[0]:
                notes["cross_section_conflict"][subject_id] = (
                    distinct[0],
                    section_names.get(other_section[subject_id], str(other_section[subject_id])),
                    other_section_sem[subject_id],
                )
        elif len(distinct) >= 2:
            resolution[subject_id] = distinct[0]  # deterministic: lowest
            notes["conflict"][subject_id] = distinct
        elif subject_id in other_section:
            resolution[subject_id] = fallback_semester   # safe fallback
            notes["section_mismatch"][subject_id] = section_names.get(
                other_section[subject_id], str(other_section[subject_id])
            )
        else:
            resolution[subject_id] = fallback_semester   # unassigned / legacy
            notes["unassigned"].append(subject_id)

    return resolution, notes


def _sections_by_ids(section_ids):
    from academics.models import Section

    return Section.objects.filter(pk__in=section_ids)


def build_sf10_workbook(student, grade_level, options=None):
    """
    Returns (openpyxl.Workbook, warnings: list[str]).

    Raises SF10ExportError for unsupported grade levels or when the learner
    has no enrollment at that grade level.

    ``options`` (optional free text, no schema): admission_date,
    adviser_name, authorized_person, date_checked.
    """
    options = options or {}
    warnings = []

    config = _sheet_config(grade_level)
    enrollments = _enrollments_for(student, grade_level)
    if not enrollments:
        raise SF10ExportError(
            f"{student} has no enrollment in {grade_level} — the SF10 needs the "
            "learner's section, track and school year. Import or encode the SF1 first."
        )

    workbook = openpyxl.load_workbook(TEMPLATE_PATH)
    worksheet = workbook[config["sheet"]]

    # ---------------- learner information (FRONT only) ----------------
    front = workbook["FRONT"]
    learner_cells = FRONT["learner"]
    front[learner_cells["last_name"]] = (student.last_name or "").upper()
    front[learner_cells["first_name"]] = (student.first_name or "").upper()
    front[learner_cells["middle_name"]] = (student.middle_name or "").upper()
    front[learner_cells["name_extension"]] = student.name_extension or ""
    front[learner_cells["lrn"]] = student.lrn
    front[learner_cells["birth_date"]] = (
        student.birth_date.strftime("%m/%d/%Y") if student.birth_date else ""
    )
    # The template validates this cell against a FEMALE/MALE list.
    front[learner_cells["gender"]] = (student.gender or "").upper()
    if options.get("admission_date"):
        front[learner_cells["admission_date"]] = options["admission_date"]

    # ---------------- per-semester scholastic record ----------------
    summary_rows_used = {}      # summary_row -> final grade
    quarter_columns_left_blank = False
    formula_cells_replaced = []

    # Build the semester plan. Each semester block is driven by an
    # enrollment (for its section/track/header) plus the subjects whose
    # SubjectAssignment.semester matches. This lets a single SchoolYear
    # populate BOTH blocks: one enrollment can serve both semesters when
    # the school year holds both semesters' subject assignments.
    semester_plan = _build_semester_plan(enrollments, grade_level)

    # Resolve every graded subject to exactly one semester block, computed
    # PER driving enrollment (its own school year + section). This supports
    # both configurations without dropping any subject:
    #   * one SchoolYear carrying both semesters (single driving enrollment)
    #   * separate SchoolYears/enrollments per semester (two driving
    #     enrollments — each resolved against its OWN year's assignments).
    # Keyed by (school_year_id, subject_id) so a subject from semester 2's
    # school year is resolved with that year's assignments, not the first.
    resolution = {}                 # (school_year_id, subject_id) -> "1"|"2"
    subject_name_by_id = {}
    aggregated_notes = {
        "unassigned": [],           # (school_year_id, subject_id)
        "section_mismatch": {},     # (school_year_id, subject_id) -> section name
        "conflict": {},             # (school_year_id, subject_id) -> [sem, sem]
        "cross_section_conflict": {},  # (year, subject) -> (own_sem, sec, other_sem)
        "legacy_years": set(),      # school_year_ids with no semester anywhere
    }

    # Distinct driving enrollments, preserving order (sem1 first).
    driving_enrollments = []
    for semester in ("1", "2"):
        enrollment = semester_plan[semester]
        if enrollment is not None and enrollment not in driving_enrollments:
            driving_enrollments.append(enrollment)

    # Which block(s) each enrollment drives. When an enrollment drives only
    # one block, a NULL/unassigned/mismatch subject falls back to THAT
    # block's semester (two-enrollment case). When one enrollment drives
    # both blocks (single-SchoolYear case), fallback stays "1" (First),
    # preserving existing behavior.
    driven_semesters = {}
    for semester in ("1", "2"):
        enrollment = semester_plan[semester]
        if enrollment is not None:
            driven_semesters.setdefault(id(enrollment), []).append(semester)

    for enrollment in driving_enrollments:
        resolution_year = enrollment.school_year
        resolution_section = enrollment.section
        roles = driven_semesters.get(id(enrollment), ["1"])
        fallback_semester = roles[0] if len(roles) == 1 else "1"
        all_graded = build_sf9_data(student, resolution_year)["subjects"]
        graded_ids = [entry["subject"].pk for entry in all_graded]
        for entry in all_graded:
            subject_name_by_id[entry["subject"].pk] = entry["subject"].name

        year_resolution, year_notes = _resolve_subject_semesters(
            resolution_year, resolution_section, graded_ids, fallback_semester
        )
        for subject_id, sem in year_resolution.items():
            resolution[(resolution_year.pk, subject_id)] = sem
        for subject_id in year_notes["unassigned"]:
            aggregated_notes["unassigned"].append((resolution_year.pk, subject_id))
        for subject_id, name in year_notes["section_mismatch"].items():
            aggregated_notes["section_mismatch"][(resolution_year.pk, subject_id)] = name
        for subject_id, semesters in year_notes["conflict"].items():
            aggregated_notes["conflict"][(resolution_year.pk, subject_id)] = semesters
        for subject_id, detail in year_notes["cross_section_conflict"].items():
            aggregated_notes["cross_section_conflict"][(resolution_year.pk, subject_id)] = detail
        if year_notes["legacy_all_null"] and year_resolution:
            aggregated_notes["legacy_years"].add(resolution_year.pk)

    # ---- surface resolution warnings once ----
    for year_id in aggregated_notes["legacy_years"]:
        # Name the block these subjects actually went to for this year.
        block_sems = {
            resolution.get((year_id, subject_id), "1")
            for (yid, subject_id) in aggregated_notes["unassigned"]
            if yid == year_id
        }
        block_word = SEMESTER_WORD[sorted(block_sems)[0]] if block_sems else "First"
        warnings.append(
            "No semester information is set on this school year's subject "
            f"assignments — all graded subjects were placed in the {block_word} "
            "Semester block. Set SubjectAssignment.semester to split them "
            "correctly."
        )
    for year_id, subject_id in aggregated_notes["unassigned"]:
        if year_id in aggregated_notes["legacy_years"]:
            continue  # already covered by the single legacy message
        block_word = SEMESTER_WORD[resolution.get((year_id, subject_id), "1")]
        warnings.append(
            f"'{subject_name_by_id.get(subject_id, subject_id)}' has no semester "
            f"on its subject assignment — it was placed in the {block_word} "
            "Semester block. Set its SubjectAssignment.semester to correct this."
        )
    for (year_id, subject_id), other_section in aggregated_notes["section_mismatch"].items():
        block_word = SEMESTER_WORD[resolution.get((year_id, subject_id), "1")]
        warnings.append(
            f"'{subject_name_by_id.get(subject_id, subject_id)}' is assigned to "
            f"section '{other_section}', not the learner's enrolled section — it "
            f"was placed in the {block_word} Semester block as a safe fallback. "
            "Please verify the assignment."
        )
    for (year_id, subject_id), semesters in aggregated_notes["conflict"].items():
        labels = ", ".join(SEMESTER_WORD.get(s, s) for s in semesters)
        warnings.append(
            f"'{subject_name_by_id.get(subject_id, subject_id)}' has conflicting "
            f"semester assignments ({labels}) for the learner's section — it was "
            f"placed in the {SEMESTER_WORD[semesters[0]]} Semester block. Please "
            "resolve the duplicate assignment."
        )
    for (year_id, subject_id), detail in aggregated_notes["cross_section_conflict"].items():
        own_sem, other_section_name, other_sem = detail
        warnings.append(
            f"'{subject_name_by_id.get(subject_id, subject_id)}' is set to "
            f"{SEMESTER_WORD[own_sem]} Semester for the learner's section, but "
            f"section '{other_section_name}' assigns it to "
            f"{SEMESTER_WORD[other_sem]} Semester. The learner's own section was "
            "used; please verify the cross-section assignment."
        )

    placed_subject_ids = set()   # subjects ACTUALLY written (never both blocks)
    overflow_subjects = []       # (semester, subject_name) that could not fit

    for semester, enrollment in semester_plan.items():
        if enrollment is None:
            continue
        block = config["blocks"][semester]
        school_year = enrollment.school_year

        # -------- block header --------
        worksheet[block["school"]] = settings.SCHOOL_NAME
        worksheet[block["school_id"]] = getattr(settings, "SCHOOL_ID", "")
        worksheet[block["grade_level"]] = _grade_level_digit(grade_level)
        worksheet[block["section"]] = enrollment.section.name if enrollment.section else ""
        worksheet[block["track"]] = (
            enrollment.section.track_strand if enrollment.section else ""
        )
        worksheet[block["school_year"]] = str(school_year)
        worksheet[block["semester"]] = SEMESTER_WORD[semester]

        if school_year.period_count != 3:
            warnings.append(
                f"{school_year} is not a 3-term school year — its grades were still "
                "written into the semestral grade column, but please verify."
            )

        # -------- subjects (resolved to this semester, de-duplicated) --------
        data = build_sf9_data(student, school_year)
        all_subjects = data["subjects"]
        subjects = [
            entry
            for entry in all_subjects
            if resolution.get((school_year.pk, entry["subject"].pk)) == semester
            and entry["subject"].pk not in placed_subject_ids
        ]
        if not subjects:
            warnings.append(
                f"No {SEMESTER_WORD[semester].lower()}-semester subjects with grades "
                f"were found for {school_year} — that block's subject rows were left "
                "blank."
            )

        core_rows = _core_rows(worksheet, block)
        next_free_row = block["last_core_row"] + 1
        capacity_reported = False

        for entry in subjects:
            subject_name = entry["subject"].name
            final_grade = entry["final_grade"]

            row = core_rows.get(_normalize(subject_name))
            if row is None:
                if next_free_row > block["last_row"]:
                    # No row capacity left: record the subject by name so it
                    # is explicitly reported, and do NOT mark it placed.
                    overflow_subjects.append((semester, subject_name))
                    capacity_reported = True
                    continue
                row = next_free_row
                next_free_row += 1
                worksheet[f"{SUBJECT_COL}{row}"] = subject_name
                # The template validates this cell against CORE/ACADEMIC/TECHPRO.
                worksheet[f"{TRACK_TYPE_COL}{row}"] = "CORE"

            # The subject now occupies a row in this block — mark it written
            # so it can never also be written into the other block.
            placed_subject_ids.add(entry["subject"].pk)

            if final_grade is None:
                warnings.append(
                    f"{subject_name} ({school_year}) has no Final Grade yet — its "
                    "semestral grade cell was left blank."
                )
                continue

            # Semestral grade: exact under 3-Term (mean of the three terms).
            target = f"{SEMESTRAL_GRADE_COL}{row}"
            if _is_formula(worksheet[target].value):
                formula_cells_replaced.append(target)
            worksheet[target] = final_grade

            # Action Taken is a formula on elective rows (it reads T and still
            # works); on the pre-printed core rows the cell is empty, so it is
            # written here.
            action_cell = f"{ACTION_TAKEN_COL}{row}"
            if not _is_formula(worksheet[action_cell].value):
                worksheet[action_cell] = (
                    "PASSED" if final_grade >= PASSING_GRADE else "FAILED"
                )

            summary_rows_used[row + block["summary_offset"]] = (
                subject_name,
                final_grade,
                row,
            )

        quarter_columns_left_blank = True

    # ---- H-1: name every subject that could not fit its block ----
    if overflow_subjects:
        for semester, subject_name in overflow_subjects:
            warnings.append(
                f"'{subject_name}' could not be written to the "
                f"{SEMESTER_WORD[semester]} Semester block — it is full "
                "(the official SF10 form has a fixed number of rows). Use an "
                "additional SF10 sheet for the remaining learning areas."
            )

    # ---------------- summary of final grades ----------------
    summary = config["summary"]
    for summary_row, (subject_name, final_grade, _source_row) in summary_rows_used.items():
        if not (summary["first_row"] <= summary_row <= summary["last_row"]):
            continue
        # The summary's subject cells are array formulas that mirror the
        # semester blocks — only fill them when nothing is there at all.
        if not worksheet[f"{SUBJECT_COL}{summary_row}"].value:
            worksheet[f"{SUBJECT_COL}{summary_row}"] = subject_name
            worksheet[f"{TRACK_TYPE_COL}{summary_row}"] = "CORE"

        target = f"{SUMMARY_FINAL_COL}{summary_row}"
        if _is_formula(worksheet[target].value):
            formula_cells_replaced.append(target)
        worksheet[target] = final_grade

    # ---------------- signatures / dates ----------------
    if options.get("adviser_name"):
        for cell in ("A46", "A85") if config is FRONT else ("A23", "A58"):
            worksheet[cell] = options["adviser_name"].upper()
    if options.get("authorized_person"):
        for cell in ("L46", "L85") if config is FRONT else ("L23", "L58"):
            worksheet[cell] = options["authorized_person"].upper()
    if options.get("date_checked"):
        for cell in ("W46", "W85") if config is FRONT else ("W23", "W58"):
            worksheet[cell] = options["date_checked"]

    # ---------------- documented limitations ----------------
    if quarter_columns_left_blank:
        warnings.append(
            "3-Term limitation: the Q1-Q4 quarterly columns were left blank because "
            "this school year is graded in three terms, which cannot be written into "
            "two quarter columns. The semestral grade and the summary Final Grade "
            "carry the computed grades, and the General Average recomputes from them."
        )
    if formula_cells_replaced:
        warnings.append(
            f"{len(formula_cells_replaced)} template formula cell(s) were replaced "
            "with computed values because they derive from the blank quarterly "
            "columns and would otherwise stay empty (e.g. "
            f"{', '.join(formula_cells_replaced[:4])})."
        )

    return workbook, warnings
