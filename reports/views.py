from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from django.contrib import messages

from accounts.decorators import role_required
from academics.models import GradeLevel, SchoolYear, Section
from students.models import Student
from accounts.scoping import scope_to_visible_students
from .forms import Sf9SelectForm, SF1UploadForm, SF1ExportForm
from .sf9 import build_sf9_pdf
from .services import base as form_services
from .services.sf1.importer import apply_import, classify
from .services.sf1.parser import parse_sf1_workbook
from .services.sf1.exporter import build_sf1_workbook

SF1_UPLOAD_PREFIX = "sf1"
SF1_IMPORT_ROLES = ("admin", "teacher", "adviser", "subject_teacher", "ict_coordinator")


def _ensure_can_view_student(user, student):
    if getattr(user, "is_superuser", False) or getattr(user, "role", None) in ("admin", "principal", "teacher"):
        return
    if user.role == "student" and student.user_id == user.id:
        return
    if user.role == "parent" and student.guardians.filter(pk=user.pk).exists():
        return
    raise PermissionDenied("You do not have permission to view this learner's report card.")


@login_required
@role_required("admin", "teacher", "adviser", "principal", "ict_coordinator")
def sf9_select(request):
    visible_students = scope_to_visible_students(request.user, Student.objects.all(), student_lookup="")

    if request.method == "POST":
        form = Sf9SelectForm(request.POST, student_queryset=visible_students)
        if form.is_valid():
            return redirect(
                "sf9_pdf",
                student_id=form.cleaned_data["student"].pk,
                school_year_id=form.cleaned_data["school_year"].pk,
            )
    else:
        form = Sf9SelectForm(student_queryset=visible_students)

    return render(request, "reports/select.html", {"form": form})


@login_required
@role_required("admin", "teacher", "adviser", "principal", "ict_coordinator")
def sf9_pdf(request, student_id, school_year_id):
    student = get_object_or_404(Student, pk=student_id)
    school_year = get_object_or_404(SchoolYear, pk=school_year_id)

    _ensure_can_view_student(request.user, student)

    pdf_bytes = build_sf9_pdf(student, school_year)

    filename = f"SF9_{student.last_name}_{student.first_name}_{school_year}.pdf".replace(" ", "_")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


# ===========================================================================
# SF1 Import (upload -> preview -> confirm), per approved implementation plan
# ===========================================================================

def _sf1_session_context(token):
    """Load + parse an SF1 upload session or raise 404 if it's gone."""
    path = form_services.upload_path(token, SF1_UPLOAD_PREFIX)
    if path is None:
        raise Http404("This import session has expired — please upload the SF1 file again.")
    return parse_sf1_workbook(path)


def _sf1_selection_from_session(request, token):
    selection = request.session.get(f"sf1_import_{token}")
    if not selection:
        raise Http404("This import session has expired — please upload the SF1 file again.")
    return (
        get_object_or_404(SchoolYear, pk=selection["school_year"]),
        get_object_or_404(GradeLevel, pk=selection["grade_level"]),
        get_object_or_404(Section, pk=selection["section"]),
        selection.get("semester"),
    )


def _header_mismatch_warnings(parse_result, school_year, grade_level, section):
    """Cross-check the file's own header text against the form selections."""
    warnings = []
    context_text = (parse_result.header.get("context_row") or "").upper()
    section_text = (parse_result.header.get("section_row") or "").upper()

    if str(school_year).upper() not in context_text and str(school_year) not in context_text:
        warnings.append(
            f"The file header does not mention School Year '{school_year}' — "
            "please make sure you selected the right school year."
        )
    if grade_level.name.upper() not in context_text:
        warnings.append(
            f"The file header does not mention Grade Level '{grade_level.name}' — "
            "please make sure you selected the right grade level."
        )
    if section.name.upper() not in section_text:
        warnings.append(
            f"The file header does not mention Section '{section.name}' — "
            "please make sure you selected the right section."
        )
    return warnings


@role_required(*SF1_IMPORT_ROLES)
def sf1_import(request):
    if request.method == "POST":
        form = SF1UploadForm(request.POST, request.FILES)
        if form.is_valid():
            token = form_services.save_upload(form.cleaned_data["file"], SF1_UPLOAD_PREFIX)
            request.session[f"sf1_import_{token}"] = {
                "school_year": form.cleaned_data["school_year"].pk,
                "grade_level": form.cleaned_data["grade_level"].pk,
                "section": form.cleaned_data["section"].pk,
                "semester": form.cleaned_data.get("semester") or None,
            }
            return redirect("sf1_import_preview", token=token)
    else:
        form = SF1UploadForm()

    return render(request, "reports/sf1_import.html", {"form": form})


@role_required(*SF1_IMPORT_ROLES)
def sf1_import_preview(request, token):
    school_year, grade_level, section, _semester = _sf1_selection_from_session(request, token)
    parse_result = _sf1_session_context(token)

    header_warnings = []
    if not parse_result.file_errors:
        classify(parse_result, school_year, grade_level, section)
        header_warnings = _header_mismatch_warnings(
            parse_result, school_year, grade_level, section
        )

    counts = {
        "created": 0,
        "updated": 0,
        "no_change": 0,
        "already_enrolled": 0,
        "conflict": 0,
        "skipped": len(parse_result.error_rows),
    }
    for row in parse_result.valid_rows:
        counts[row.status] += 1
        if row.enrollment_status:
            counts[row.enrollment_status] += 1

    context = {
        "token": token,
        "school_year": school_year,
        "grade_level": grade_level,
        "section": section,
        "parse_result": parse_result,
        "header_warnings": header_warnings,
        "counts": counts,
        "importable": parse_result.is_importable,
    }
    return render(request, "reports/sf1_preview.html", context)


@role_required(*SF1_IMPORT_ROLES)
@require_POST
def sf1_import_confirm(request, token):
    school_year, grade_level, section, semester = _sf1_selection_from_session(request, token)

    if request.POST.get("action") == "cancel":
        form_services.discard_upload(token, SF1_UPLOAD_PREFIX)
        request.session.pop(f"sf1_import_{token}", None)
        messages.info(request, "SF1 import cancelled — nothing was changed.")
        return redirect("sf1_import")

    # Re-parse from the stored file: the preview page is display-only and
    # nothing posted back from the browser is trusted.
    parse_result = _sf1_session_context(token)
    if parse_result.file_errors:
        messages.error(request, "The uploaded file could no longer be parsed. Nothing was imported.")
        return redirect("sf1_import_preview", token=token)

    classify(parse_result, school_year, grade_level, section)

    if not parse_result.is_importable:
        messages.error(request, "There are no importable rows in this file. Nothing was imported.")
        return redirect("sf1_import_preview", token=token)

    try:
        summary = apply_import(parse_result, school_year, grade_level, section, semester=semester)
    except Exception:
        # Atomic transaction has rolled back; keep the temp file for retry.
        messages.error(
            request,
            "An unexpected error occurred and the import was rolled back — "
            "no changes were made. Please try again.",
        )
        return redirect("sf1_import_preview", token=token)

    form_services.discard_upload(token, SF1_UPLOAD_PREFIX)
    request.session.pop(f"sf1_import_{token}", None)

    messages.success(
        request,
        f"SF1 import complete for {grade_level} - {section.name}, {school_year}: "
        f"{summary.created} created, {summary.updated} updated, "
        f"{summary.no_change} unchanged, {summary.enrolled} newly enrolled, "
        f"{summary.already_enrolled} already enrolled, "
        f"{summary.conflicts} conflicts, {summary.skipped_errors} skipped (errors).",
    )
    for detail in summary.conflict_details:
        messages.warning(request, detail)

    return redirect("sf1_import")


@role_required("admin", "teacher", "adviser", "subject_teacher", "principal", "ict_coordinator")
def sf1_export(request):
    """Generate the official SF1-SHS Excel file for a section."""
    if request.method == "POST":
        form = SF1ExportForm(request.POST)
        if form.is_valid():
            school_year = form.cleaned_data["school_year"]
            grade_level = form.cleaned_data["grade_level"]
            section = form.cleaned_data["section"]
            semester_label = dict(form.fields["semester"].choices)[
                form.cleaned_data["semester"]
            ]

            workbook, warnings = build_sf1_workbook(
                school_year, grade_level, section, semester_label
            )
            for warning in warnings:
                messages.warning(request, warning)

            filename = (
                f"SF1_{section.name}_{school_year}".replace(" ", "_").replace("/", "-")
                + ".xlsx"
            )
            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            workbook.save(response)
            return response
    else:
        form = SF1ExportForm()

    return render(request, "reports/sf1_export.html", {"form": form})


@role_required("admin", "teacher", "adviser", "subject_teacher", "principal", "ict_coordinator")
def sf2_export(request):
    """Generate the official SF2-SHS (Daily Attendance Report) Excel file."""
    from .forms import SF2ExportForm
    from .services.sf2.exporter import build_sf2_workbook

    if request.method == "POST":
        form = SF2ExportForm(request.POST)
        if form.is_valid():
            school_year = form.cleaned_data["school_year"]
            grade_level = form.cleaned_data["grade_level"]
            section = form.cleaned_data["section"]
            semester_label = dict(form.fields["semester"].choices)[
                form.cleaned_data["semester"]
            ]
            month = form.cleaned_data["month"]
            year = form.cleaned_data["year"]

            workbook, warnings = build_sf2_workbook(
                school_year, grade_level, section, semester_label, year, month
            )
            for warning in warnings:
                messages.warning(request, warning)

            month_tag = f"{year}-{month:02d}"
            filename = (
                f"SF2_{section.name}_{month_tag}".replace(" ", "_").replace("/", "-")
                + ".xlsx"
            )
            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            workbook.save(response)
            return response
    else:
        import datetime
        today = datetime.date.today()
        form = SF2ExportForm(initial={"month": today.month, "year": today.year})

    return render(request, "reports/sf2_export.html", {"form": form})


@role_required("admin", "teacher", "adviser", "principal", "ict_coordinator")
def sf9_export(request):
    """Generate the official SF9-SHS (report card) Excel file."""
    from .forms import SF9ExportForm
    from .services.sf9.exporter import SF9ExportError, build_sf9_workbook

    # Same visibility scoping the SF9 PDF uses.
    student_queryset = scope_to_visible_students(request.user, Student.objects.all())

    if request.method == "POST":
        form = SF9ExportForm(request.POST, student_queryset=student_queryset)
        if form.is_valid():
            student = form.cleaned_data["student"]
            school_year = form.cleaned_data["school_year"]
            options = {
                key: form.cleaned_data.get(key)
                for key in (
                    "adviser_name",
                    "adviser_position",
                    "principal_name",
                    "principal_position",
                    "admitted_to_grade",
                    "eligible_for_admission_to_grade",
                )
            }

            try:
                workbook, warnings = build_sf9_workbook(student, school_year, options)
            except SF9ExportError as error:
                messages.error(request, str(error))
                return redirect("sf9_export")

            for warning in warnings:
                messages.warning(request, warning)

            filename = (
                f"SF9_{student.last_name}_{school_year}".replace(" ", "_").replace("/", "-")
                + ".xlsx"
            )
            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            workbook.save(response)
            return response
    else:
        form = SF9ExportForm(student_queryset=student_queryset)

    return render(request, "reports/sf9_export.html", {"form": form})


@role_required("admin", "teacher", "adviser", "principal", "ict_coordinator")
def sf10_export(request):
    """Generate the official SF10-SHS (permanent record) Excel file."""
    from .forms import SF10ExportForm
    from .services.sf10.exporter import SF10ExportError, build_sf10_workbook

    student_queryset = scope_to_visible_students(request.user, Student.objects.all())

    if request.method == "POST":
        form = SF10ExportForm(request.POST, student_queryset=student_queryset)
        if form.is_valid():
            student = form.cleaned_data["student"]
            grade_level = form.cleaned_data["grade_level"]
            options = {
                key: form.cleaned_data.get(key)
                for key in (
                    "admission_date",
                    "adviser_name",
                    "authorized_person",
                    "date_checked",
                )
            }

            try:
                workbook, warnings = build_sf10_workbook(student, grade_level, options)
            except SF10ExportError as error:
                messages.error(request, str(error))
                return redirect("sf10_export")

            for warning in warnings:
                messages.warning(request, warning)

            filename = (
                f"SF10_{student.last_name}_{grade_level.name}".replace(" ", "_").replace("/", "-")
                + ".xlsx"
            )
            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            workbook.save(response)
            return response
    else:
        form = SF10ExportForm(student_queryset=student_queryset)

    return render(request, "reports/sf10_export.html", {"form": form})


# ---------------------------------------------------------------------------
# ID Maker views — Module 11 (D[131-137])
# Additive: no existing view, permission, or logic changed.
# ---------------------------------------------------------------------------

ID_MAKER_ROLES = (
    "admin", "principal", "ict_coordinator",
    "teacher", "adviser", "subject_teacher",
)


@role_required(*ID_MAKER_ROLES)
def id_maker_student(request):
    """
    Student ID card generator (D[133]).
    GET  — show student picker filtered to visible students.
    POST — return PDF download for the selected student(s).
    """
    from .services.id_maker.student_id import build_student_id_pdf

    student_queryset = scope_to_visible_students(
        request.user, Student.objects.all()
    )
    school_years = SchoolYear.objects.all().order_by("-is_active", "-year")
    sections     = Section.objects.select_related("grade_level").order_by("name")

    if request.method == "POST":
        student_ids = request.POST.getlist("students")
        if not student_ids:
            from django.contrib import messages
            messages.warning(request, "Please select at least one student.")
            return redirect("id_maker_student")

        students = student_queryset.filter(pk__in=student_ids)
        if not students.exists():
            from django.contrib import messages
            messages.warning(request, "No valid students found.")
            return redirect("id_maker_student")

        pdf_bytes = build_student_id_pdf(students)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="student_ids.pdf"'
        return response

    # GET — optionally filter by school year / section for the picker
    sy_id  = request.GET.get("school_year")
    sec_id = request.GET.get("section")
    sel_sy  = SchoolYear.objects.filter(pk=sy_id).first() if sy_id else None
    sel_sec = Section.objects.filter(pk=sec_id).first() if sec_id else None

    from enrollment.models import Enrollment
    if sel_sy or sel_sec:
        enr_qs = Enrollment.objects.filter(student__in=student_queryset)
        if sel_sy:
            enr_qs = enr_qs.filter(school_year=sel_sy)
        if sel_sec:
            enr_qs = enr_qs.filter(section=sel_sec)
        student_list = student_queryset.filter(
            pk__in=enr_qs.values_list("student_id", flat=True)
        ).order_by("last_name", "first_name")
    else:
        student_list = student_queryset.order_by("last_name", "first_name")

    return render(request, "reports/id_maker_student.html", {
        "students":    student_list,
        "school_years": school_years,
        "sections":    sections,
        "selected_sy":  sel_sy,
        "selected_sec": sel_sec,
    })


@role_required(*ID_MAKER_ROLES)
def id_maker_teacher(request):
    """
    Teacher ID card generator (D[134]).
    GET  — show teacher picker.
    POST — return PDF download for selected teacher(s).
    """
    from .services.id_maker.teacher_id import build_teacher_id_pdf
    from teachers.models import Teacher as TeacherModel

    if request.method == "POST":
        teacher_ids = request.POST.getlist("teachers")
        if not teacher_ids:
            from django.contrib import messages
            messages.warning(request, "Please select at least one teacher.")
            return redirect("id_maker_teacher")

        teachers = TeacherModel.objects.filter(pk__in=teacher_ids)
        if not teachers.exists():
            from django.contrib import messages
            messages.warning(request, "No valid teachers found.")
            return redirect("id_maker_teacher")

        pdf_bytes = build_teacher_id_pdf(teachers)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="teacher_ids.pdf"'
        return response

    teachers = TeacherModel.objects.order_by("last_name", "first_name")
    return render(request, "reports/id_maker_teacher.html", {
        "teachers": teachers,
    })


# ---------------------------------------------------------------------------
# Certificate Generator — Module 12 (D[138]–D[145])
# Additive: no existing view, permission, or import changed.
# ---------------------------------------------------------------------------

CERTIFICATE_ROLES = ID_MAKER_ROLES   # same staff roles as ID Maker (approved)

CERT_TYPES = {
    "enrollment":    "Certificate of Enrollment",
    "completion":    "Certificate of Completion",
    "recognition":   "Certificate of Recognition",
    "participation": "Certificate of Participation",
    "diploma":       "Diploma",
}

# Certificate types that require a free-text description field
CERT_FREE_TEXT = {"recognition", "participation"}


@role_required(*CERTIFICATE_ROLES)
def certificate_generate(request):
    """
    Certificate generator (D[138]–D[145]).
    GET  — show student picker + certificate type selector.
    POST — validate, call the matching generator, return PDF download.
    """
    from .services.certificates.generator import (
        build_enrollment_cert,
        build_completion_cert,
        build_recognition_cert,
        build_participation_cert,
        build_diploma,
    )

    student_queryset = scope_to_visible_students(
        request.user, Student.objects.all()
    )
    school_years = SchoolYear.objects.all().order_by("-is_active", "-year")
    sections     = Section.objects.select_related("grade_level").order_by("name")

    if request.method == "POST":
        student_id = request.POST.get("student")
        cert_type  = request.POST.get("cert_type")
        free_text  = request.POST.get("free_text", "").strip()

        # Validate student
        try:
            student = student_queryset.get(pk=student_id)
        except Student.DoesNotExist:
            messages.warning(request, "Please select a valid student.")
            return redirect("certificate_generate")

        # Validate certificate type
        if cert_type not in CERT_TYPES:
            messages.warning(request, "Please select a valid certificate type.")
            return redirect("certificate_generate")

        # Validate free-text for types that require it
        if cert_type in CERT_FREE_TEXT and not free_text:
            messages.warning(
                request,
                f"Please enter what the student is being "
                f"{'recognized for' if cert_type == 'recognition' else 'participating in'}."
            )
            return redirect("certificate_generate")

        # Generate PDF
        if cert_type == "enrollment":
            pdf_bytes = build_enrollment_cert(student)
        elif cert_type == "completion":
            pdf_bytes = build_completion_cert(student)
        elif cert_type == "recognition":
            pdf_bytes = build_recognition_cert(student, free_text)
        elif cert_type == "participation":
            pdf_bytes = build_participation_cert(student, free_text)
        else:  # diploma
            pdf_bytes = build_diploma(student)

        safe_name = f"{student.last_name}_{cert_type}.pdf".replace(" ", "_")
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
        return response

    # GET — optional filter by school year / section
    sy_id  = request.GET.get("school_year")
    sec_id = request.GET.get("section")
    sel_sy  = SchoolYear.objects.filter(pk=sy_id).first() if sy_id else None
    sel_sec = Section.objects.filter(pk=sec_id).first() if sec_id else None

    from enrollment.models import Enrollment
    if sel_sy or sel_sec:
        enr_qs = Enrollment.objects.filter(student__in=student_queryset)
        if sel_sy:
            enr_qs = enr_qs.filter(school_year=sel_sy)
        if sel_sec:
            enr_qs = enr_qs.filter(section=sel_sec)
        student_list = student_queryset.filter(
            pk__in=enr_qs.values_list("student_id", flat=True)
        ).order_by("last_name", "first_name")
    else:
        student_list = student_queryset.order_by("last_name", "first_name")

    return render(request, "reports/certificates.html", {
        "students":    student_list,
        "cert_types":  CERT_TYPES,
        "free_text_types": list(CERT_FREE_TEXT),
        "school_years": school_years,
        "sections":    sections,
        "selected_sy":  sel_sy,
        "selected_sec": sel_sec,
    })


# ---------------------------------------------------------------------------
# SF1 PDF Print — D[063] (additive — existing sf1_export view not changed)
# Same roles, same form, same data source as the Excel export.
# ---------------------------------------------------------------------------

@role_required("admin", "teacher", "adviser", "subject_teacher", "principal", "ict_coordinator")
def sf1_pdf_export(request):
    """
    Generate the SF1-SHS as a landscape-letter PDF (D[063] Print SF1 PDF).
    Reuses SF1ExportForm, same allowed roles as sf1_export.
    """
    from .services.sf1.pdf import build_sf1_pdf

    if request.method == "POST":
        form = SF1ExportForm(request.POST)
        if form.is_valid():
            school_year    = form.cleaned_data["school_year"]
            grade_level    = form.cleaned_data["grade_level"]
            section        = form.cleaned_data["section"]
            semester_label = dict(form.fields["semester"].choices)[
                form.cleaned_data["semester"]
            ]

            pdf_bytes = build_sf1_pdf(
                school_year, grade_level, section, semester_label
            )

            filename = (
                f"SF1_{section.name}_{school_year}"
                .replace(" ", "_").replace("/", "-")
                + ".pdf"
            )
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
    else:
        form = SF1ExportForm()

    return render(request, "reports/sf1_export.html", {"form": form, "show_pdf_button": True})
