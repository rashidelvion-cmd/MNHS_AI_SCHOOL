from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from accounts.scoping import scope_to_visible_students
from django.db.models import Prefetch, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from enrollment.models import Enrollment
from .models import Student
from .forms import StudentForm


@login_required
def student_list(request):
    students = scope_to_visible_students(
        request.user, Student.objects.all(), student_lookup=""
    )

    # Search — D[064] Search Student
    # Applied after scoping so a student/parent cannot search outside
    # their own visible set.
    q = request.GET.get("q", "").strip()
    if q:
        students = students.filter(
            Q(lrn__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )

    # Load each student's enrollments in one query (no N+1), ordered so the
    # current one comes first: the active school year, then the most recent
    # enrollment (Enrollment already defaults to -date_enrolled).
    enrollment_qs = Enrollment.objects.select_related(
        "grade_level", "section", "school_year"
    ).order_by("-school_year__is_active", "-date_enrolled")
    students = students.prefetch_related(
        Prefetch("enrollment_set", queryset=enrollment_qs, to_attr="ordered_enrollments")
    )

    # Attach the current enrollment (first of the ordered list) for the template.
    student_rows = []
    for student in students:
        enrollments = getattr(student, "ordered_enrollments", [])
        student.current_enrollment = enrollments[0] if enrollments else None
        student_rows.append(student)

    return render(
        request,
        "students/student_list.html",
        {
            "students":    student_rows,
            "q":           q,
            "total_count": Student.objects.filter(
                pk__in=scope_to_visible_students(
                    request.user, Student.objects.all(), student_lookup=""
                ).values_list("pk", flat=True)
            ).count(),
        }
    )


@role_required("admin", "ict_coordinator", "teacher", "adviser")
def add_student(request):

    if request.method == "POST":
        form = StudentForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()
            return redirect("student_list")

    else:
        form = StudentForm()

    return render(
        request,
        "students/add_student.html",
        {
            "form": form
        }
    )


@role_required("admin", "ict_coordinator", "teacher", "adviser")
def edit_student(request, pk):

    student = get_object_or_404(Student, pk=pk)

    if request.method == "POST":
        form = StudentForm(request.POST, request.FILES, instance=student)

        if form.is_valid():
            form.save()
            return redirect("student_list")

    else:
        form = StudentForm(instance=student)

    return render(
        request,
        "students/add_student.html",
        {
            "form": form
        }
    )

@role_required("admin", "principal")
@require_POST
def delete_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    student.delete()
    return redirect("student_list")