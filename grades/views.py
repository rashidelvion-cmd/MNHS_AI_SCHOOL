from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from accounts.scoping import scope_to_visible_students
from django.shortcuts import render, redirect
from .models import Grade
from .forms import GradeForm


@login_required
def grade_list(request):

    grades = scope_to_visible_students(request.user, Grade.objects.all(), student_lookup="student")

    return render(
        request,
        "grades/grade_list.html",
        {
            "grades": grades
        }
    )


@role_required("admin", "principal", "teacher")
def add_grade(request):

    if request.method == "POST":

        form = GradeForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("grade_list")

    else:

        form = GradeForm()

    return render(
        request,
        "grades/add_grade.html",
        {
            "form": form
        }
    )

# ---------------------------------------------------------------------------
# Ranking and Awards views (additive — no existing code modified)
# Roles: all staff — DOCX places no restriction on teacher/subject teacher
# ---------------------------------------------------------------------------

RANKING_ROLES = (
    "admin", "principal", "ict_coordinator",
    "teacher", "adviser", "subject_teacher",
)


@role_required(*RANKING_ROLES)
def class_ranking_view(request):
    """Ranked list of all students by General Average for a school year/section."""
    from academics.models import SchoolYear, Section
    from .services import class_ranking

    school_years = SchoolYear.objects.all().order_by("-is_active", "-year")
    sections     = Section.objects.select_related("grade_level").order_by("name")

    sy_id  = request.GET.get("school_year")
    sec_id = request.GET.get("section")
    sel_sy  = SchoolYear.objects.filter(pk=sy_id).first() if sy_id else SchoolYear.objects.filter(is_active=True).first()
    sel_sec = Section.objects.filter(pk=sec_id).first() if sec_id else None

    rows = class_ranking(sel_sy, sel_sec) if sel_sy else []

    return render(request, "grades/class_ranking.html", {
        "school_years":    school_years,
        "sections":        sections,
        "selected_sy":     sel_sy,
        "selected_section": sel_sec,
        "rows":            rows,
    })


@role_required(*RANKING_ROLES)
def subject_ranking_view(request):
    """Students ranked by a single subject's Final Grade."""
    from academics.models import SchoolYear, Section, Subject
    from .services import subject_ranking

    school_years = SchoolYear.objects.all().order_by("-is_active", "-year")
    subjects     = Subject.objects.order_by("name")
    sections     = Section.objects.select_related("grade_level").order_by("name")

    sy_id   = request.GET.get("school_year")
    subj_id = request.GET.get("subject")
    sec_id  = request.GET.get("section")
    sel_sy   = SchoolYear.objects.filter(pk=sy_id).first() if sy_id else SchoolYear.objects.filter(is_active=True).first()
    sel_subj = Subject.objects.filter(pk=subj_id).first() if subj_id else None
    sel_sec  = Section.objects.filter(pk=sec_id).first() if sec_id else None

    rows = subject_ranking(sel_sy, sel_subj, sel_sec) if sel_sy and sel_subj else []

    return render(request, "grades/subject_ranking.html", {
        "school_years":    school_years,
        "subjects":        subjects,
        "sections":        sections,
        "selected_sy":     sel_sy,
        "selected_subject": sel_subj,
        "selected_section": sel_sec,
        "rows":            rows,
    })


@role_required(*RANKING_ROLES)
def awards_list_view(request):
    """Awards recipients grouped by honor level for a school year/section."""
    from academics.models import SchoolYear, Section
    from .services import awards_list

    school_years = SchoolYear.objects.all().order_by("-is_active", "-year")
    sections     = Section.objects.select_related("grade_level").order_by("name")

    sy_id  = request.GET.get("school_year")
    sec_id = request.GET.get("section")
    sel_sy  = SchoolYear.objects.filter(pk=sy_id).first() if sy_id else SchoolYear.objects.filter(is_active=True).first()
    sel_sec = Section.objects.filter(pk=sec_id).first() if sec_id else None

    groups = awards_list(sel_sy, sel_sec) if sel_sy else {}

    return render(request, "grades/awards_list.html", {
        "school_years":    school_years,
        "sections":        sections,
        "selected_sy":     sel_sy,
        "selected_section": sel_sec,
        "groups":          groups,
    })


# ---------------------------------------------------------------------------
# Grade Locking — D[094]
# lock_grade:   admin + principal only (Q1 approved)
# unlock_grade: admin only             (Q2 approved)
# Both use Grade.objects.update() to bypass save() lock check on the
# is_locked field itself.
# ---------------------------------------------------------------------------

from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_POST


@require_POST
@role_required("admin", "principal")
def lock_grade(request, pk):
    """Set Grade.is_locked = True. Admin and principal only (Q1)."""
    grade = get_object_or_404(Grade, pk=pk)
    if grade.is_locked:
        messages.info(request, f"Grade for {grade.student} / {grade.subject} is already locked.")
    else:
        Grade.objects.filter(pk=pk).update(is_locked=True)
        messages.success(request, f"Grade for {grade.student} / {grade.subject} has been locked.")
    return redirect("grade_list")


@require_POST
@role_required("admin")
def unlock_grade(request, pk):
    """Set Grade.is_locked = False. Admin only (Q2)."""
    grade = get_object_or_404(Grade, pk=pk)
    if not grade.is_locked:
        messages.info(request, f"Grade for {grade.student} / {grade.subject} is not locked.")
    else:
        Grade.objects.filter(pk=pk).update(is_locked=False)
        messages.success(request, f"Grade for {grade.student} / {grade.subject} has been unlocked.")
    return redirect("grade_list")


# ---------------------------------------------------------------------------
# Grade Verification — D[095]
# verify_grade:   admin + principal (Q1)
# unverify_grade: admin only        (Q2)
# Q3-A: Grade.save() resets is_verified; these views use .update() to
#        bypass save() so the verify/unverify action itself is not reset.
# Q4-A: independent of is_locked — no lock check here.
# Q5-A: unverification is supported and reversible.
# ---------------------------------------------------------------------------


@require_POST
@role_required("admin", "principal")
def verify_grade(request, pk):
    """Set Grade.is_verified = True.  Admin and principal only (Q1)."""
    grade = get_object_or_404(Grade, pk=pk)
    if grade.is_verified:
        messages.info(
            request,
            f"Grade for {grade.student} / {grade.subject} is already verified.",
        )
    else:
        Grade.objects.filter(pk=pk).update(is_verified=True)
        messages.success(
            request,
            f"Grade for {grade.student} / {grade.subject} has been verified.",
        )
    return redirect("grade_list")


@require_POST
@role_required("admin")
def unverify_grade(request, pk):
    """Set Grade.is_verified = False.  Admin only (Q2)."""
    grade = get_object_or_404(Grade, pk=pk)
    if not grade.is_verified:
        messages.info(
            request,
            f"Grade for {grade.student} / {grade.subject} is not verified.",
        )
    else:
        Grade.objects.filter(pk=pk).update(is_verified=False)
        messages.success(
            request,
            f"Grade for {grade.student} / {grade.subject} has been unverified.",
        )
    return redirect("grade_list")
