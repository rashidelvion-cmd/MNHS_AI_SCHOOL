from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from accounts.scoping import scope_to_visible_students
from django.shortcuts import render, redirect
from .models import Attendance
from .forms import AttendanceForm


@login_required
def attendance_list(request):

    attendance = scope_to_visible_students(request.user, Attendance.objects.all(), student_lookup="student")

    return render(
        request,
        "attendance/attendance_list.html",
        {
            "attendance": attendance
        }
    )


@role_required("admin", "ict_coordinator", "teacher", "adviser", "subject_teacher")
def add_attendance(request):

    if request.method == "POST":

        form = AttendanceForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("attendance_list")

    else:

        form = AttendanceForm()

    return render(
        request,
        "attendance/add_attendance.html",
        {
            "form": form
        }
    )

# ===========================================================================
# Bulk attendance marking (SF2 workflow) — additive; existing views untouched
# ===========================================================================

from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
import datetime

from academics.models import SchoolYear, Section
from enrollment.models import Enrollment
from .forms import AttendanceMarkSelectForm

BULK_STATUSES = ("Present", "Absent", "Late")


@role_required("admin", "principal", "teacher", "adviser", "subject_teacher", "ict_coordinator")
def attendance_mark_select(request):
    if request.method == "POST":
        form = AttendanceMarkSelectForm(request.POST)
        if form.is_valid():
            return redirect(
                "attendance_mark_sheet",
                school_year_id=form.cleaned_data["school_year"].pk,
                section_id=form.cleaned_data["section"].pk,
                date=form.cleaned_data["date"].isoformat(),
            )
    else:
        form = AttendanceMarkSelectForm()

    return render(request, "attendance/mark_select.html", {"form": form})


@role_required("admin", "teacher", "adviser", "subject_teacher", "ict_coordinator")
def attendance_mark_sheet(request, school_year_id, section_id, date):
    school_year = get_object_or_404(SchoolYear, pk=school_year_id)
    section = get_object_or_404(Section, pk=section_id)

    try:
        target_date = datetime.date.fromisoformat(date)
    except ValueError:
        raise Http404("Invalid date.")

    enrollments = (
        Enrollment.objects.filter(school_year=school_year, section=section)
        .select_related("student")
        .order_by("student__gender", "student__last_name", "student__first_name")
    )
    students = [e.student for e in enrollments]

    if not students:
        messages.error(
            request,
            f"No learners are enrolled in {section} for {school_year} — "
            "import or encode the SF1 first.",
        )
        return redirect("attendance_mark_select")

    existing = {
        a.student_id: a
        for a in Attendance.objects.filter(
            student__in=students, date=target_date
        )
    }

    if request.method == "POST":
        with transaction.atomic():
            saved = 0
            for student in students:
                status = request.POST.get(f"status_{student.pk}", "Present")
                if status not in BULK_STATUSES:
                    status = "Present"
                remarks = (request.POST.get(f"remarks_{student.pk}") or "").strip()[:200]
                Attendance.objects.update_or_create(
                    student=student,
                    date=target_date,
                    defaults={"status": status, "remarks": remarks},
                )
                saved += 1
        messages.success(
            request,
            f"Attendance saved for {section} on {target_date:%b %d, %Y} "
            f"({saved} learners).",
        )
        return redirect(
            "attendance_mark_sheet",
            school_year_id=school_year.pk,
            section_id=section.pk,
            date=target_date.isoformat(),
        )

    rows = []
    for student in students:
        record = existing.get(student.pk)
        rows.append(
            {
                "student": student,
                "status": record.status if record else "Present",
                "remarks": record.remarks if record else "",
            }
        )

    context = {
        "school_year": school_year,
        "section": section,
        "target_date": target_date,
        "rows": rows,
        "statuses": BULK_STATUSES,
        "already_recorded": bool(existing),
    }
    return render(request, "attendance/mark_sheet.html", context)


# ===========================================================================
# QR Attendance — Module 13 (D[146-149])
# Approved workflow:
#   Staff creates session (school_year + section + date → UUID token → QR)
#   Student scans QR on own phone (authenticated)
#   System records Attendance(student, date=session.date, status="Present")
#   SF2 reads Attendance automatically (exporter unchanged)
# Approved decisions: D1-β staff-selected date, D2-α status="Present"
# ===========================================================================

import io
import json

import qrcode as qrcode_lib
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from .models import QRAttendanceSession
from academics.models import SchoolYear, Section
from students.models import Student


QR_SESSION_ROLES = (
    "admin", "principal", "ict_coordinator",
    "teacher", "adviser", "subject_teacher",
)


@role_required(*QR_SESSION_ROLES)
def qr_session_create(request):
    """
    Staff view: create a QR attendance session.
    GET  – render form (school year, section, date).
    POST – create QRAttendanceSession, re-render with QR code displayed.
    The QR code shown on this page is what students scan.
    """
    school_years = SchoolYear.objects.all().order_by("-is_active", "-year")
    sections     = Section.objects.select_related("grade_level").order_by("name")
    session_obj  = None
    qr_data_url  = None

    if request.method == "POST":
        sy_id   = request.POST.get("school_year")
        sec_id  = request.POST.get("section")
        date_str = request.POST.get("date")

        sy  = SchoolYear.objects.filter(pk=sy_id).first()
        sec = Section.objects.filter(pk=sec_id).first()

        if not (sy and sec and date_str):
            messages.warning(request, "Please fill in all fields.")
        else:
            import datetime
            try:
                att_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                messages.warning(request, "Invalid date format.")
                att_date = None

            if att_date:
                session_obj = QRAttendanceSession.objects.create(
                    school_year=sy,
                    section=sec,
                    date=att_date,
                    created_by=request.user,
                )
                # Build the scan URL encoded in the QR
                scan_url = request.build_absolute_uri(
                    f"/attendance/qr/scan/{session_obj.token}/"
                )
                # Generate QR as base64 PNG for inline display
                qr = qrcode_lib.make(scan_url)
                buf = io.BytesIO()
                qr.save(buf, format="PNG")
                import base64
                qr_data_url = (
                    "data:image/png;base64,"
                    + base64.b64encode(buf.getvalue()).decode()
                )

    return render(request, "attendance/qr_session_create.html", {
        "school_years": school_years,
        "sections":     sections,
        "session":      session_obj,
        "qr_data_url":  qr_data_url,
    })


@role_required(*QR_SESSION_ROLES)
def qr_session_list(request):
    """Staff view: list of all QR attendance sessions."""
    sessions = QRAttendanceSession.objects.select_related(
        "school_year", "section", "created_by"
    ).all()
    return render(request, "attendance/qr_session_list.html", {
        "sessions": sessions,
    })


@login_required
def qr_scan(request, token):
    """
    Student-facing QR scan endpoint — GET only.

    Approved workflow (D[146-149]):
        Student scans QR with phone → phone opens this URL (HTTP GET)
        → server identifies student from request.user
        → Attendance.objects.update_or_create immediately
        → server renders HTML result (success / already recorded / error)

    No confirmation step. No POST. No AJAX. No JsonResponse.
    Attendance is recorded as soon as the authenticated student opens this URL.
    Student identity: request.user → Student.user (approved).
    Date: session.date (D1-β, staff-selected).
    Status: "Present" (D2-α, approved).
    """
    session_obj = get_object_or_404(QRAttendanceSession, token=token)

    # Identify student from the authenticated user (approved mechanism)
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return render(request, "attendance/qr_scan.html", {
            "session": session_obj,
            "result":  "unlinked",
        })

    # Record attendance immediately — no confirmation step
    _, created = Attendance.objects.update_or_create(
        student=student,
        date=session_obj.date,
        defaults={"status": "Present"},
    )

    return render(request, "attendance/qr_scan.html", {
        "session":          session_obj,
        "student":          student,
        "result":           "created" if created else "already_recorded",
        "attendance_date":  session_obj.date,
    })


# ---------------------------------------------------------------------------
# Face Recognition Attendance — M-4Jul (Messenger)
# Q1-A: OpenCV LBPH  Q2: confidence<100  Q3: 2s interval  Q4: admin/ict/principal
# Q5: date = today (automatic)
# Additive — QR and manual attendance views NOT modified.
# ---------------------------------------------------------------------------

import base64
import json
import datetime as _dt

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

FACE_TRAIN_ROLES = ("admin", "ict_coordinator", "principal")
FACE_SCAN_ROLES  = ("admin", "principal", "ict_coordinator",
                    "teacher", "adviser", "subject_teacher")


@role_required(*FACE_TRAIN_ROLES)
def face_train(request):
    """
    Train (or retrain) the LBPH face model from all student reference photos.
    Only students with an uploaded photo are trained; others are skipped.
    Roles: admin, ict_coordinator, principal (Q4).
    """
    from students.models import Student
    from .services_face import train_model

    result = None
    if request.method == "POST":
        students = Student.objects.exclude(photo="").exclude(photo=None)
        result   = train_model(list(students))

    return render(request, "attendance/face_train.html", {"result": result})


@role_required(*FACE_SCAN_ROLES)
def face_attendance(request):
    """
    Render the camera page. Teacher selects section then points mobile camera
    at students. A frame is captured every 2 seconds (Q3) and sent to face_scan.
    Roles: all six staff roles.
    """
    sy_list  = __import__("academics.models", fromlist=["SchoolYear"]).SchoolYear.objects.all().order_by("-is_active", "-year")
    sec_list = __import__("academics.models", fromlist=["Section"]).Section.objects.select_related("grade_level").order_by("name")
    return render(request, "attendance/face_attendance.html", {
        "school_years": sy_list,
        "sections":     sec_list,
    })


@csrf_exempt
@role_required(*FACE_SCAN_ROLES)
def face_scan(request):
    """
    AJAX endpoint called every 2 seconds by the camera page (Q3).
    Receives a base64 JPEG frame, runs LBPH recognition, and if a student is
    recognised records Attendance(student, date=today, status="Present") (Q5).
    Returns JSON result to the browser.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    from .services_face import recognise_face
    from enrollment.models import Enrollment

    try:
        body = json.loads(request.body)
        frame_b64  = body.get("frame", "")
        sy_id      = int(body.get("school_year_id", 0))
        section_id = int(body.get("section_id", 0))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return JsonResponse({"success": False, "message": f"Bad request: {exc}"}, status=400)

    # Decode base64 frame
    try:
        if "," in frame_b64:            # strip data:image/jpeg;base64, prefix
            frame_b64 = frame_b64.split(",", 1)[1]
        frame_bytes = base64.b64decode(frame_b64)
    except Exception as exc:
        return JsonResponse({"success": False, "message": f"Frame decode error: {exc}"}, status=400)

    # Students enrolled in this section
    enrolled_pks = list(
        Enrollment.objects.filter(
            school_year_id=sy_id, section_id=section_id
        ).values_list("student_id", flat=True)
    )
    if not enrolled_pks:
        return JsonResponse({
            "success": False, "face_detected": False,
            "message": "No students enrolled in this section for the selected school year.",
        })

    # Recognise
    result = recognise_face(frame_bytes, enrolled_pks)

    # Record attendance if recognised
    if result["success"]:
        today = _dt.date.today()   # Q5: always today
        _, created = Attendance.objects.update_or_create(
            student_id=result["student_pk"],
            date=today,
            defaults={"status": "Present"},
        )
        result["already_recorded"] = not created
        result["date"] = str(today)

    return JsonResponse(result)
