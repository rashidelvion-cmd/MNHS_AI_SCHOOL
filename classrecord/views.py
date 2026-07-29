from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from academics.models import Subject, SchoolYear
from students.models import Student
from grades.models import Grade
from .forms import ClassRecordSelectForm, ScoreItemForm
from .models import ScoreItem, COMPONENT_CHOICES
from .services import compute_quarterly_grade, QUARTER_FIELD_MAP

STAFF_ROLES = ("admin", "principal", "ict_coordinator", "teacher", "adviser", "subject_teacher")


@role_required(*STAFF_ROLES)
def class_record_select(request):
    if request.method == "POST":
        form = ClassRecordSelectForm(request.POST)
        if form.is_valid():
            return redirect(
                "class_record_detail",
                student_id=form.cleaned_data["student"].pk,
                subject_id=form.cleaned_data["subject"].pk,
                school_year_id=form.cleaned_data["school_year"].pk,
                quarter=form.cleaned_data["quarter"],
            )
    else:
        form = ClassRecordSelectForm()

    return render(request, "classrecord/select.html", {"form": form})


@role_required(*STAFF_ROLES)
def class_record_detail(request, student_id, subject_id, school_year_id, quarter):
    student = get_object_or_404(Student, pk=student_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    school_year = get_object_or_404(SchoolYear, pk=school_year_id)
    quarter = int(quarter)

    item_form = ScoreItemForm()

    quarterly_grade, breakdown = compute_quarterly_grade(student, subject, school_year, quarter)

    component_labels = dict(COMPONENT_CHOICES)
    for code, data in breakdown.items():
        data["label"] = component_labels.get(code, code)

    context = {
        "student": student,
        "subject": subject,
        "school_year": school_year,
        "quarter": quarter,
        "period_label": school_year.period_label(quarter),
        "item_form": item_form,
        "breakdown": breakdown,
        "quarterly_grade": quarterly_grade,
    }
    return render(request, "classrecord/detail.html", context)


@role_required(*STAFF_ROLES)
@require_POST
def add_score_item(request, student_id, subject_id, school_year_id, quarter):
    student = get_object_or_404(Student, pk=student_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    school_year = get_object_or_404(SchoolYear, pk=school_year_id)

    form = ScoreItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.student = student
        item.subject = subject
        item.school_year = school_year
        item.quarter = int(quarter)
        item.save()
        messages.success(request, "Score item added.")
    else:
        messages.error(request, "Could not add score item — please check the values.")

    return redirect(
        "class_record_detail",
        student_id=student_id,
        subject_id=subject_id,
        school_year_id=school_year_id,
        quarter=quarter,
    )


@role_required(*STAFF_ROLES)
@require_POST
def delete_score_item(request, pk):
    item = get_object_or_404(ScoreItem, pk=pk)
    student_id, subject_id, school_year_id, quarter = (
        item.student_id,
        item.subject_id,
        item.school_year_id,
        item.quarter,
    )
    item.delete()
    messages.success(request, "Score item removed.")

    return redirect(
        "class_record_detail",
        student_id=student_id,
        subject_id=subject_id,
        school_year_id=school_year_id,
        quarter=quarter,
    )


@role_required(*STAFF_ROLES)
@require_POST
def save_to_grade(request, student_id, subject_id, school_year_id, quarter):
    student = get_object_or_404(Student, pk=student_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    school_year = get_object_or_404(SchoolYear, pk=school_year_id)
    quarter = int(quarter)

    if quarter > school_year.period_count:
        messages.error(
            request,
            f"{school_year} uses {school_year.get_grading_system_display()} — "
            f"period {quarter} does not apply.",
        )
        return redirect("class_record_select")

    quarterly_grade, _ = compute_quarterly_grade(student, subject, school_year, quarter)

    if quarterly_grade is None:
        messages.error(request, "Enter at least one score before saving to the Grade record.")
        return redirect(
            "class_record_detail",
            student_id=student_id,
            subject_id=subject_id,
            school_year_id=school_year_id,
            quarter=quarter,
        )

    grade, _created = Grade.objects.get_or_create(
        student=student,
        subject=subject,
        school_year=school_year,
        defaults={
            "first_quarter": 0,
            "second_quarter": 0,
            "third_quarter": 0,
            "fourth_quarter": 0,
        },
    )
    setattr(grade, QUARTER_FIELD_MAP[quarter], quarterly_grade)
    grade.save()  # Grade.save() auto-recomputes final_grade from the 4 quarters.

    messages.success(
        request,
        f"Quarter {quarter} grade ({quarterly_grade}) saved to {student}'s {subject} record.",
    )
    return redirect("grade_list")


# ===========================================================================
# Official E-Class Record grid (roster-wide) — additive; the per-student
# Class Record pages above remain unchanged.
# ===========================================================================

from decimal import Decimal, InvalidOperation

from django.db import transaction

from academics.models import SubjectAssignment
from enrollment.models import Enrollment
from .forms import AssessmentForm, ECRSelectForm
from .models import Assessment
from .services import compute_grades, get_weights, sync_grade

ECR_ROLES = ("admin", "teacher", "adviser", "subject_teacher")

# Official E-Class Record column order: Written Work, then Performance
# Task, then Quarterly Assessment (the model's default ordering is
# alphabetical, which is not the form's order).
COMPONENT_ORDER = {"WW": 0, "PT": 1, "QA": 2}


def _ordered_assessments(assignment, quarter):
    return sorted(
        Assessment.objects.filter(subject_assignment=assignment, quarter=quarter),
        key=lambda a: (COMPONENT_ORDER.get(a.component, 9), a.order, a.pk),
    )


def _ecr_students(assignment):
    """Roster of the assignment's section for its school year (SF1 chain)."""
    enrollments = (
        Enrollment.objects.filter(
            school_year=assignment.school_year, section=assignment.section
        )
        .select_related("student")
        .order_by("student__gender", "student__last_name", "student__first_name")
    )
    return [enrollment.student for enrollment in enrollments]


@role_required(*ECR_ROLES)
def ecr_select(request):
    if request.method == "POST":
        form = ECRSelectForm(request.POST)
        if form.is_valid():
            return redirect(
                "ecr_grid",
                assignment_id=form.cleaned_data["subject_assignment"].pk,
                quarter=int(form.cleaned_data["quarter"]),
            )
    else:
        form = ECRSelectForm()

    return render(request, "classrecord/ecr_select.html", {"form": form})


@role_required(*ECR_ROLES)
def ecr_grid(request, assignment_id, quarter):
    assignment = get_object_or_404(
        SubjectAssignment.objects.select_related(
            "subject", "section", "teacher", "school_year"
        ),
        pk=assignment_id,
    )
    quarter = int(quarter)
    school_year = assignment.school_year
    subject = assignment.subject

    if quarter > school_year.period_count:
        messages.error(
            request,
            f"{school_year} uses {school_year.get_grading_system_display()} — "
            f"period {quarter} does not apply.",
        )
        return redirect("ecr_select")

    students = _ecr_students(assignment)
    if not students:
        messages.error(
            request,
            f"No learners are enrolled in {assignment.section} for {school_year} — "
            "import the SF1 first.",
        )
        return redirect("ecr_select")

    assessments = _ordered_assessments(assignment, quarter)

    if request.method == "POST":
        return _ecr_save(request, assignment, quarter, students, assessments)

    scores = {
        (item.student_id, item.assessment_id): item
        for item in ScoreItem.objects.filter(
            assessment__in=assessments, student__in=students
        )
    }

    by_component = {code: [] for code, _label in COMPONENT_CHOICES}
    for assessment in assessments:
        by_component[assessment.component].append(assessment)

    rows = []
    for student in students:
        initial_grade, term_grade, _breakdown = compute_grades(
            student, subject, school_year, quarter
        )
        rows.append(
            {
                "student": student,
                "cells": [
                    {
                        "assessment": assessment,
                        "value": (
                            scores[(student.pk, assessment.pk)].raw_score
                            if (student.pk, assessment.pk) in scores
                            else ""
                        ),
                    }
                    for assessment in assessments
                ],
                "initial_grade": initial_grade,
                "term_grade": term_grade,
            }
        )

    context = {
        "assignment": assignment,
        "school_year": school_year,
        "quarter": quarter,
        "period_label": school_year.period_label(quarter),
        "assessments": assessments,
        "by_component": by_component,
        "component_labels": dict(COMPONENT_CHOICES),
        "rows": rows,
        "assessment_form": AssessmentForm(),
        "weights": get_weights(subject),
    }
    return render(request, "classrecord/ecr_grid.html", context)


class _ECRValidationError(Exception):
    """Raised inside the grid transaction to force a full rollback."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _ecr_save(request, assignment, quarter, students, assessments):
    """Save the whole grid in one atomic transaction, then auto-sync grades."""
    errors = []

    try:
        with transaction.atomic():
            for student in students:
                for assessment in assessments:
                    field = f"score_{student.pk}_{assessment.pk}"
                    raw_value = (request.POST.get(field) or "").strip()

                    if raw_value == "":
                        # Blank = not administered / not yet encoded.
                        ScoreItem.objects.filter(
                            student=student, assessment=assessment
                        ).delete()
                        continue

                    try:
                        score = Decimal(raw_value)
                    except (InvalidOperation, ValueError):
                        errors.append(f"{student}: '{raw_value}' is not a number.")
                        continue

                    if score < 0 or score > assessment.highest_score:
                        errors.append(
                            f"{student} — {assessment.label}: {score} is outside "
                            f"0..{assessment.highest_score}."
                        )
                        continue

                    ScoreItem.objects.update_or_create(
                        student=student,
                        assessment=assessment,
                        defaults={
                            "subject": assignment.subject,
                            "school_year": assignment.school_year,
                            "quarter": quarter,
                            "component": assessment.component,
                            "label": assessment.label,
                            "raw_score": score,
                            "highest_score": assessment.highest_score,
                        },
                    )

            if errors:
                raise _ECRValidationError(errors)

            # Auto-sync: transmuted Term Grade -> Grade record for every learner.
            synced = 0
            for student in students:
                if sync_grade(student, assignment.subject, assignment.school_year, quarter) is not None:
                    synced += 1

    except _ECRValidationError as error:
        # Nothing was saved — the whole grid rolled back.
        for message in error.errors[:10]:
            messages.error(request, message)
        if len(error.errors) > 10:
            messages.error(request, f"...and {len(error.errors) - 10} more problem(s).")
        messages.error(request, "No scores were saved — please correct the values and save again.")
        return redirect("ecr_grid", assignment_id=assignment.pk, quarter=quarter)

    messages.success(
        request,
        f"E-Class Record saved — {synced} learner grade(s) computed and "
        "updated in the Grade records.",
    )
    return redirect("ecr_grid", assignment_id=assignment.pk, quarter=quarter)


@role_required(*ECR_ROLES)
@require_POST
def ecr_add_assessment(request, assignment_id, quarter):
    assignment = get_object_or_404(SubjectAssignment, pk=assignment_id)
    form = AssessmentForm(request.POST)
    if form.is_valid():
        assessment = form.save(commit=False)
        assessment.subject_assignment = assignment
        assessment.quarter = int(quarter)
        last = (
            Assessment.objects.filter(
                subject_assignment=assignment,
                quarter=int(quarter),
                component=assessment.component,
            )
            .order_by("-order")
            .first()
        )
        assessment.order = (last.order + 1) if last else 1
        assessment.save()
        messages.success(request, f"Added {assessment.get_component_display()}: {assessment.label}.")
    else:
        messages.error(request, "Could not add the assessment — please check the values.")

    return redirect("ecr_grid", assignment_id=assignment_id, quarter=quarter)


@role_required(*ECR_ROLES)
@require_POST
def ecr_delete_assessment(request, pk):
    assessment = get_object_or_404(
        Assessment.objects.select_related("subject_assignment"), pk=pk
    )
    assignment = assessment.subject_assignment
    quarter = assessment.quarter
    students = _ecr_students(assignment)

    with transaction.atomic():
        assessment.delete()  # cascades to its ScoreItems
        for student in students:
            sync_grade(student, assignment.subject, assignment.school_year, quarter)

    messages.success(request, "Assessment removed and grades recomputed.")
    return redirect("ecr_grid", assignment_id=assignment.pk, quarter=quarter)


# ---------------------------------------------------------------------------
# ECR Export — M-7Jul (Messenger: "send the softcopy to the Adviser or else
# generate E-ClassRecord with grades")
# Roles: same as ECR_ROLES — admin, teacher, adviser, subject_teacher (Q2-A)
# Format: Excel + PDF (Q1-C)
# Additive — ecr_grid view is not modified.
# ---------------------------------------------------------------------------

@role_required(*ECR_ROLES)
def ecr_export_excel(request, assignment_id, quarter):
    """Download the ECR as an .xlsx workbook (M-7Jul)."""
    from .services_export import build_ecr_excel
    from academics.models import SubjectAssignment

    assignment = get_object_or_404(
        SubjectAssignment.objects.select_related(
            "subject", "section", "teacher", "school_year"
        ),
        pk=assignment_id,
    )
    quarter = int(quarter)
    xlsx_bytes = build_ecr_excel(assignment, quarter)

    filename = (
        f"ECR_{assignment.subject}_{assignment.section}"
        f"_{assignment.school_year}_Q{quarter}.xlsx"
        .replace(" ", "_").replace("/", "-")
    )
    from django.http import HttpResponse
    response = HttpResponse(
        xlsx_bytes,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@role_required(*ECR_ROLES)
def ecr_export_pdf(request, assignment_id, quarter):
    """Download the ECR as a landscape-letter PDF (M-7Jul)."""
    from .services_export import build_ecr_pdf
    from academics.models import SubjectAssignment
    from django.http import HttpResponse

    assignment = get_object_or_404(
        SubjectAssignment.objects.select_related(
            "subject", "section", "teacher", "school_year"
        ),
        pk=assignment_id,
    )
    quarter = int(quarter)
    pdf_bytes = build_ecr_pdf(assignment, quarter)

    filename = (
        f"ECR_{assignment.subject}_{assignment.section}"
        f"_{assignment.school_year}_Q{quarter}.pdf"
        .replace(" ", "_").replace("/", "-")
    )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
