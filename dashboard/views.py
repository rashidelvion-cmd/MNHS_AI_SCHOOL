"""
Role-branching dashboard view.

One URL (/dashboard/) — the view builds a role-specific context and
renders a single shared template that uses role-if blocks to show only
the relevant cards, charts, and quick-action links per user type.

No new FK or schema change. Adviser/Subject Teacher dashboards use
querystring pickers where no staff-to-record FK exists.
"""

import json
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils.safestring import mark_safe

from academics.models import Section, SchoolYear, SubjectAssignment
from attendance.models import Attendance
from enrollment.models import Enrollment
from grades.models import Grade
from academics.models import Event
from students.models import Student
from teachers.models import Teacher

User = get_user_model()
PASSING = 75


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _active_sy():
    return SchoolYear.objects.filter(is_active=True).first()


def _today_att_rate(sy=None, section=None):
    today = date.today()
    qs = Attendance.objects.filter(date=today)
    if sy and section:
        ids = Enrollment.objects.filter(
            school_year=sy, section=section
        ).values_list("student_id", flat=True)
        qs = qs.filter(student_id__in=ids)
    total = qs.count()
    if not total:
        return "N/A"
    present = qs.filter(status__in=("Present", "Late")).count()
    return f"{round(present / total * 100)}%"


def _promotion_rate(sy):
    if not sy:
        return "N/A"
    enrolled = set(
        Enrollment.objects.filter(school_year=sy).values_list("student_id", flat=True)
    )
    if not enrolled:
        return "N/A"
    has_grade = set(
        Grade.objects.filter(school_year=sy, final_grade__isnull=False)
        .values_list("student_id", flat=True)
    )
    failed = set(
        Grade.objects.filter(school_year=sy, final_grade__lt=PASSING)
        .values_list("student_id", flat=True)
    )
    promoted = len(enrolled & has_grade - failed)
    return f"{round(promoted / len(enrolled) * 100)}%"


def _dropout_rate(sy):
    if not sy:
        return "N/A"
    ids = Enrollment.objects.filter(school_year=sy).values_list("student_id", flat=True)
    total = ids.count()
    if not total:
        return "N/A"
    dropouts = Student.objects.filter(pk__in=ids).filter(
        Q(remarks_code__icontains="T/O") | Q(remarks_code__icontains="NLS")
    ).count()
    return f"{round(dropouts / total * 100)}%"


def _enroll_trend():
    rows = (
        Enrollment.objects.values("school_year__year")
        .annotate(n=Count("id"))
        .order_by("school_year__year")
    )
    return {
        "labels": [r["school_year__year"] or "?" for r in rows],
        "data":   [r["n"] for r in rows],
    }


def _att_trend(days=30, sy=None, section=None):
    since = date.today() - timedelta(days=days)
    qs = Attendance.objects.filter(date__gte=since)
    if sy and section:
        ids = Enrollment.objects.filter(
            school_year=sy, section=section
        ).values_list("student_id", flat=True)
        qs = qs.filter(student_id__in=ids)
    rows = qs.values("date", "status").annotate(n=Count("id")).order_by("date")
    by_date = {}
    for r in rows:
        d = str(r["date"])
        by_date.setdefault(d, {"P": 0, "A": 0})
        if r["status"] in ("Present", "Late"):
            by_date[d]["P"] += r["n"]
        else:
            by_date[d]["A"] += r["n"]
    labels = sorted(by_date)
    return {
        "labels":  labels,
        "present": [by_date[d]["P"] for d in labels],
        "absent":  [by_date[d]["A"] for d in labels],
    }


def _grade_dist(sy):
    qs = Grade.objects.filter(final_grade__isnull=False)
    if sy:
        qs = qs.filter(school_year=sy)
    bands = {
        "Below 75": Q(final_grade__lt=75),
        "75 – 79":  Q(final_grade__gte=75, final_grade__lt=80),
        "80 – 84":  Q(final_grade__gte=80, final_grade__lt=85),
        "85 – 89":  Q(final_grade__gte=85, final_grade__lt=90),
        "90 – 100": Q(final_grade__gte=90),
    }
    return {
        "labels": list(bands),
        "data":   [qs.filter(q).count() for q in bands.values()],
    }


def _js(obj):
    return mark_safe(json.dumps(obj))


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------


def _get_upcoming_events(n=5):
    """Next N upcoming events — added to every role dashboard (R1/R2/R3)."""
    from datetime import date
    return list(
        Event.objects.filter(event_date__gte=date.today())
        .order_by("event_date", "event_time")[:n]
    )


@login_required(login_url="login")
def dashboard(request):
    role = request.user.role
    sy   = _active_sy()

    # ---- ADMIN ----
    if role == "admin":
        et = _enroll_trend()
        at = _att_trend(30)
        gd = _grade_dist(sy)
        ctx = dict(
            role=role, sy=sy,
            total_students=Student.objects.count(),
            total_teachers=Teacher.objects.count(),
            total_users=User.objects.count(),
            total_sections=Section.objects.count(),
            attendance_rate=_today_att_rate(),
            promotion_rate=_promotion_rate(sy),
            dropout_rate=_dropout_rate(sy),
            enroll_labels=_js(et["labels"]), enroll_data=_js(et["data"]),
            att_labels=_js(at["labels"]), att_present=_js(at["present"]),
            att_absent=_js(at["absent"]),
            grade_labels=_js(gd["labels"]), grade_data=_js(gd["data"]),
            upcoming_events=_get_upcoming_events(),
        )

    # ---- PRINCIPAL ----
    elif role == "principal":
        at = _att_trend(30)
        gd = _grade_dist(sy)
        ctx = dict(
            role=role, sy=sy,
            total_students=Student.objects.count(),
            total_teachers=Teacher.objects.count(),
            attendance_rate=_today_att_rate(),
            promotion_rate=_promotion_rate(sy),
            dropout_rate=_dropout_rate(sy),
            att_labels=_js(at["labels"]), att_present=_js(at["present"]),
            att_absent=_js(at["absent"]),
            grade_labels=_js(gd["labels"]), grade_data=_js(gd["data"]),
            upcoming_events=_get_upcoming_events(),
        )

    # ---- ICT COORDINATOR ----
    elif role == "ict_coordinator":
        adviser_count = User.objects.filter(role="adviser").count()
        subj_count    = User.objects.filter(role="subject_teacher").count()
        teacher_count = User.objects.filter(
            role__in=("teacher", "adviser", "subject_teacher")
        ).count()
        sections_sf1 = list(
            Enrollment.objects.filter(school_year=sy)
            .values("section__name")
            .annotate(n=Count("id"))
            .order_by("section__name")
        ) if sy else []
        et = _enroll_trend()
        at = _att_trend(30)
        ctx = dict(
            role=role, sy=sy,
            total_students=Student.objects.count(),
            total_teachers=teacher_count,
            adviser_count=adviser_count,
            subj_teacher_count=subj_count,
            total_sections=Section.objects.count(),
            attendance_rate=_today_att_rate(),
            sections_sf1=sections_sf1,
            enroll_labels=_js(et["labels"]), enroll_data=_js(et["data"]),
            att_labels=_js(at["labels"]), att_present=_js(at["present"]),
            att_absent=_js(at["absent"]),
            upcoming_events=_get_upcoming_events(),
        )

    # ---- ADVISER (section picker) ----
    elif role == "adviser":
        sections  = Section.objects.select_related("grade_level").order_by("name")
        sec_id    = request.GET.get("section")
        sel_sec   = Section.objects.filter(pk=sec_id).first() if sec_id else None
        my_students   = []
        grades_entered = 0
        at = {"labels": [], "present": [], "absent": []}
        if sel_sec and sy:
            enrs = Enrollment.objects.filter(
                school_year=sy, section=sel_sec
            ).select_related("student")
            my_students = [e.student for e in enrs]
            at = _att_trend(30, sy, sel_sec)
            grades_entered = Grade.objects.filter(
                student__in=my_students, school_year=sy,
                final_grade__isnull=False
            ).count()
        ctx = dict(
            role=role, sy=sy,
            sections=sections, selected_section=sel_sec,
            my_students=my_students, student_count=len(my_students),
            attendance_rate=_today_att_rate(sy, sel_sec),
            grades_entered=grades_entered,
            att_labels=_js(at["labels"]), att_present=_js(at["present"]),
            att_absent=_js(at["absent"]),
            upcoming_events=_get_upcoming_events(),
        )

    # ---- SUBJECT TEACHER (teacher picker) ----
    elif role == "subject_teacher":
        teachers    = Teacher.objects.order_by("last_name", "first_name")
        teacher_id  = request.GET.get("teacher")
        sel_teacher = Teacher.objects.filter(pk=teacher_id).first() if teacher_id else None
        subject_summary = []
        total_students  = 0
        if sel_teacher and sy:
            asgs = SubjectAssignment.objects.filter(
                school_year=sy, teacher=sel_teacher
            ).select_related("subject", "section")
            seen = set()
            for a in asgs:
                sids = list(
                    Enrollment.objects.filter(
                        school_year=sy, section=a.section
                    ).values_list("student_id", flat=True)
                )
                seen.update(sids)
                done = Grade.objects.filter(
                    student_id__in=sids, subject=a.subject,
                    school_year=sy, final_grade__isnull=False,
                ).count()
                subject_summary.append({
                    "subject":  a.subject.name,
                    "section":  a.section.name,
                    "semester": a.get_semester_display() if a.semester else "—",
                    "students": len(sids),
                    "grades_done": done,
                })
            total_students = len(seen)
        ctx = dict(
            role=role, sy=sy,
            teachers=teachers, selected_teacher=sel_teacher,
            subject_count=len(subject_summary),
            total_students=total_students,
            subject_summary=subject_summary,
            upcoming_events=_get_upcoming_events(),
        )

    # ---- STUDENT ----
    elif role == "student":
        student = Student.objects.filter(user=request.user).first()
        enrollment = my_grades = None
        general_avg = None
        if student:
            enrollment = (
                Enrollment.objects
                .filter(student=student)
                .select_related("grade_level", "section", "school_year")
                .order_by("-school_year__is_active", "-date_enrolled")
                .first()
            )
            if enrollment:
                my_grades = (
                    Grade.objects.filter(
                        student=student,
                        school_year=enrollment.school_year,
                        final_grade__isnull=False,
                    )
                    .select_related("subject")
                    .order_by("subject__name")
                )
                if my_grades:
                    general_avg = round(
                        sum(float(g.final_grade) for g in my_grades) / my_grades.count()
                    )
        ctx = dict(
            role=role, student=student,
            enrollment=enrollment, my_grades=my_grades, general_avg=general_avg,
            upcoming_events=_get_upcoming_events(),
        )

    # ---- PARENT ----
    elif role == "parent":
        children  = Student.objects.filter(guardians=request.user)
        child_id  = request.GET.get("child")
        sel_child = children.filter(pk=child_id).first() if child_id else children.first()
        child_enroll = child_grades = None
        recent_att = []
        att_summary = {"present": 0, "absent": 0, "late": 0}
        if sel_child:
            child_enroll = (
                Enrollment.objects.filter(student=sel_child)
                .select_related("grade_level", "section", "school_year")
                .order_by("-school_year__is_active", "-date_enrolled")
                .first()
            )
            if child_enroll:
                child_grades = (
                    Grade.objects.filter(
                        student=sel_child,
                        school_year=child_enroll.school_year,
                        final_grade__isnull=False,
                    )
                    .select_related("subject")
                    .order_by("subject__name")
                )
            since = date.today() - timedelta(days=30)
            recent_att = list(
                Attendance.objects.filter(
                    student=sel_child, date__gte=since
                ).order_by("-date")[:30]
            )
            for a in recent_att:
                if a.status == "Present":  att_summary["present"] += 1
                elif a.status == "Absent": att_summary["absent"]  += 1
                elif a.status == "Late":   att_summary["late"]    += 1
        ctx = dict(
            role=role,
            children=children, sel_child=sel_child,
            child_enroll=child_enroll, child_grades=child_grades,
            att_summary=att_summary, recent_att=recent_att,
            upcoming_events=_get_upcoming_events(),
        )

    # ---- FALLBACK (generic teacher / superuser) ----
    else:
        at = _att_trend(30)
        ctx = dict(
            role=role, sy=sy,
            total_students=Student.objects.count(),
            total_teachers=Teacher.objects.count(),
            attendance_rate=_today_att_rate(),
            att_labels=_js(at["labels"]), att_present=_js(at["present"]),
            att_absent=_js(at["absent"]),
            upcoming_events=_get_upcoming_events(),
        )

    return render(request, "dashboard/dashboard.html", ctx)
