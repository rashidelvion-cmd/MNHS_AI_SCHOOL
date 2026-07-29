from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from accounts.scoping import scope_to_visible_students
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .models import Enrollment
from .forms import EnrollmentForm


@login_required
def enrollment_list(request):
    enrollments = scope_to_visible_students(request.user, Enrollment.objects.all(), student_lookup="student")

    return render(
        request,
        "enrollment/enrollment_list.html",
        {
            "enrollments": enrollments
        }
    )


@role_required("admin", "principal", "teacher")
def add_enrollment(request):

    if request.method == "POST":
        form = EnrollmentForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("enrollment_list")

    else:
        form = EnrollmentForm()

    return render(
        request,
        "enrollment/add_enrollment.html",
        {
            "form": form
        }
    )


@role_required("admin", "principal", "teacher")
def edit_enrollment(request, pk):

    enrollment = get_object_or_404(Enrollment, pk=pk)

    if request.method == "POST":
        form = EnrollmentForm(request.POST, instance=enrollment)

        if form.is_valid():
            form.save()
            return redirect("enrollment_list")

    else:
        form = EnrollmentForm(instance=enrollment)

    return render(
        request,
        "enrollment/add_enrollment.html",
        {
            "form": form
        }
    )


@role_required("admin", "principal")
@require_POST
def delete_enrollment(request, pk):

    enrollment = get_object_or_404(Enrollment, pk=pk)
    enrollment.delete()

    return redirect("enrollment_list")