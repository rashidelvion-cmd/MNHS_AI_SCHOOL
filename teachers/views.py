from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .models import Teacher
from .forms import TeacherForm


@role_required("admin", "principal", "ict_coordinator", "teacher", "adviser", "subject_teacher")
def teacher_list(request):
    teachers = Teacher.objects.all()
    return render(request, "teachers/teacher_list.html", {
        "teachers": teachers
    })


@role_required("admin", "principal")
def add_teacher(request):

    if request.method == "POST":
        form = TeacherForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("teacher_list")

    else:
        form = TeacherForm()

    return render(request, "teachers/add_teacher.html", {
        "form": form
    })


@role_required("admin", "principal")
def edit_teacher(request, pk):

    teacher = get_object_or_404(Teacher, pk=pk)

    if request.method == "POST":
        form = TeacherForm(request.POST, instance=teacher)

        if form.is_valid():
            form.save()
            return redirect("teacher_list")

    else:
        form = TeacherForm(instance=teacher)

    return render(request, "teachers/add_teacher.html", {
        "form": form
    })


@role_required("admin", "principal")
@require_POST
def delete_teacher(request, pk):

    teacher = get_object_or_404(Teacher, pk=pk)

    teacher.delete()

    return redirect("teacher_list")