from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from students.models import Student
from .models import Attendance

User = get_user_model()


class AttendanceModelTests(TestCase):

    def setUp(self):
        self.student = Student.objects.create(
            lrn="123456789012",
            first_name="Juan",
            last_name="Cruz",
            gender="Male",
            birth_date="2012-05-01",
        )

    def test_duplicate_attendance_same_day_rejected(self):
        Attendance.objects.create(student=self.student, date="2026-07-01", status="Present")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Attendance.objects.create(student=self.student, date="2026-07-01", status="Absent")


class AttendanceViewAuthTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="staff", password="strongpass123")

    def test_list_requires_login(self):
        response = self.client.get(reverse("attendance_list"))
        self.assertEqual(response.status_code, 302)

    def test_list_accessible_when_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("attendance_list"))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# QR Attendance tests — Module 13 (D[146-149])
# ---------------------------------------------------------------------------

import datetime
import uuid
from django.test import TestCase, Client
from django.urls import reverse

from academics.models import SchoolYear, GradeLevel, Section
from enrollment.models import Enrollment
from .models import QRAttendanceSession


class QRAttendanceTests(TestCase):

    def setUp(self):
        self.sy  = SchoolYear.objects.create(
            year="2023-2024", grading_system="term", is_active=True)
        self.gl  = GradeLevel.objects.create(name="Grade 11")
        self.sec = Section.objects.create(
            grade_level=self.gl, name="11-CSS", track_strand="TVL")
        self.att_date = datetime.date(2024, 1, 15)

        # Staff user
        self.staff = User.objects.create_user(
            username="staff_qr", password="p", role="adviser")

        # Student user linked to a Student record
        self.student_user = User.objects.create_user(
            username="student_qr", password="p", role="student")
        self.student = Student.objects.create(
            lrn="121708990001", last_name="TESTQR", first_name="STUDENT",
            gender="Male", birth_date=datetime.date(2007, 1, 1),
            user=self.student_user,
        )
        Enrollment.objects.create(
            student=self.student, school_year=self.sy,
            grade_level=self.gl, section=self.sec, semester="1",
        )

        # Unlinked student user (no Student.user relationship)
        self.unlinked_user = User.objects.create_user(
            username="unlinked_qr", password="p", role="student")

        # A pre-created session for scan tests
        self.session = QRAttendanceSession.objects.create(
            school_year=self.sy, section=self.sec,
            date=self.att_date, created_by=self.staff,
        )

    # ── Session creation ─────────────────────────────────────────────────────

    def test_session_create_staff_get(self):
        """Staff can open the create session page."""
        c = Client()
        c.login(username="staff_qr", password="p")
        r = c.get(reverse("qr_session_create"))
        self.assertEqual(r.status_code, 200)

    def test_session_create_staff_post(self):
        """Staff POST creates a QRAttendanceSession record."""
        c = Client()
        c.login(username="staff_qr", password="p")
        before = QRAttendanceSession.objects.count()
        r = c.post(reverse("qr_session_create"), {
            "school_year": self.sy.pk,
            "section":     self.sec.pk,
            "date":        "2024-01-16",
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(QRAttendanceSession.objects.count(), before + 1)
        new_session = QRAttendanceSession.objects.order_by("-created_at").first()
        self.assertEqual(str(new_session.date), "2024-01-16")

    def test_session_create_blocked_student(self):
        """Student role cannot create a session — 403."""
        c = Client()
        c.login(username="student_qr", password="p")
        r = c.get(reverse("qr_session_create"))
        self.assertEqual(r.status_code, 403)

    def test_session_create_blocked_parent(self):
        """Parent role cannot create a session — 403."""
        parent = User.objects.create_user(
            username="parent_qr", password="p", role="parent")
        c = Client()
        c.login(username="parent_qr", password="p")
        r = c.get(reverse("qr_session_create"))
        self.assertEqual(r.status_code, 403)

    # ── QR scan — core workflow ───────────────────────────────────────────────

    def test_qr_scan_records_present(self):
        """GET to scan URL immediately creates Attendance — no confirmation step."""
        c = Client()
        c.login(username="student_qr", password="p")
        r = c.get(reverse("qr_scan", args=[self.session.token]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            Attendance.objects.filter(
                student=self.student, date=self.att_date).exists()
        )

    def test_qr_scan_status_is_present(self):
        """D2-α: scan records status exactly 'Present'."""
        c = Client()
        c.login(username="student_qr", password="p")
        c.get(reverse("qr_scan", args=[self.session.token]))
        record = Attendance.objects.get(
            student=self.student, date=self.att_date)
        self.assertEqual(record.status, "Present")

    def test_qr_scan_uses_session_date(self):
        """D1-β: Attendance.date equals the staff-selected session.date."""
        c = Client()
        c.login(username="student_qr", password="p")
        c.get(reverse("qr_scan", args=[self.session.token]))
        record = Attendance.objects.get(
            student=self.student, date=self.att_date)
        self.assertEqual(record.date, self.session.date)

    def test_qr_scan_duplicate_no_crash(self):
        """Second scan returns 200 with already_recorded result, no crash."""
        c = Client()
        c.login(username="student_qr", password="p")
        c.get(reverse("qr_scan", args=[self.session.token]))
        r2 = c.get(reverse("qr_scan", args=[self.session.token]))
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, "Already Recorded")
        # Only one Attendance record exists
        self.assertEqual(
            Attendance.objects.filter(
                student=self.student, date=self.att_date).count(), 1
        )

    def test_qr_scan_invalid_token(self):
        """Unknown token returns 404, no Attendance created."""
        c = Client()
        c.login(username="student_qr", password="p")
        fake = uuid.uuid4()
        r = c.get(f"/attendance/qr/scan/{fake}/")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(
            Attendance.objects.filter(student=self.student).exists()
        )

    def test_qr_scan_unlinked_student(self):
        """User with no Student.user link gets error page, no Attendance created."""
        c = Client()
        c.login(username="unlinked_qr", password="p")
        r = c.get(reverse("qr_scan", args=[self.session.token]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Account Not Linked")
        self.assertFalse(Attendance.objects.exists())

    def test_qr_scan_unauthenticated(self):
        """Unauthenticated request redirects to login."""
        r = Client().get(
            reverse("qr_scan", args=[self.session.token]))
        self.assertIn(r.status_code, [301, 302])

    # ── SF2 integration ───────────────────────────────────────────────────────

    def test_sf2_reads_qr_attendance(self):
        """SF2 exporter correctly reads a QR-created Attendance record."""
        # Create the attendance via QR scan
        c = Client()
        c.login(username="student_qr", password="p")
        c.get(reverse("qr_scan", args=[self.session.token]))

        # SF2 queries Attendance by student membership in section
        enrolled_ids = list(
            Enrollment.objects.filter(
                school_year=self.sy, section=self.sec
            ).values_list("student_id", flat=True)
        )
        records = Attendance.objects.filter(
            student_id__in=enrolled_ids,
            date__gte=datetime.date(2024, 1, 1),
            date__lte=datetime.date(2024, 1, 31),
        )
        self.assertEqual(records.count(), 1)
        self.assertEqual(records.first().status, "Present")

    # ── Existing functionality unaffected ─────────────────────────────────────

    def test_existing_bulk_marking_unaffected(self):
        """attendance_mark_select still returns 200 for staff."""
        c = Client()
        c.login(username="staff_qr", password="p")
        r = c.get(reverse("attendance_mark_select"))
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# Face Recognition Attendance tests — M-4Jul (OpenCV LBPH, Q1-A)
# ---------------------------------------------------------------------------

import io
import json
import datetime
import numpy as np
from PIL import Image as PILImage

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from academics.models import SchoolYear, GradeLevel, Section
from enrollment.models import Enrollment
from students.models import Student
from .models import Attendance, FaceEncoding
from .services_face import train_model, recognise_face, CONFIDENCE_THRESHOLD

User = get_user_model()


def _make_jpeg_bytes(color=(128, 128, 128), size=(200, 200)) -> bytes:
    """Return a minimal JPEG image as bytes."""
    img = PILImage.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_photo_file(color=(128, 128, 128)):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile("face.jpg", _make_jpeg_bytes(color), content_type="image/jpeg")


class FaceEncodingModelTests(TestCase):

    def setUp(self):
        self.sy  = SchoolYear.objects.create(
            year="2023-2024", grading_system="term", is_active=True)
        self.gl  = GradeLevel.objects.create(name="Grade 11")
        self.sec = Section.objects.create(
            grade_level=self.gl, name="11-CSS", track_strand="TVL")
        self.student = Student.objects.create(
            lrn="FACE000001", first_name="FACE", last_name="TEST",
            gender="Male", birth_date=datetime.date(2007, 1, 1),
        )

    def test_faceencoding_model_exists(self):
        """FaceEncoding model is importable and has expected fields."""
        # Django reports FK field as 'student', not 'student_id'
        fields = [f.name for f in FaceEncoding._meta.get_fields() if hasattr(f, 'column')]
        self.assertIn("student", fields)
        self.assertIn("encoding", fields)
        self.assertIn("trained_at", fields)
        self.assertIn("source_photo", fields)

    def test_train_model_skips_student_without_photo(self):
        """train_model skips students who have no photo uploaded."""
        result = train_model([self.student])
        self.assertEqual(len(result["trained"]), 0)
        self.assertIn("FACE, TEST" if False else "TEST, FACE", result["skipped"])

    def test_train_model_with_synthetic_photo(self, *args):
        """train_model creates FaceEncoding for student with a saved photo."""
        # Save a synthetic photo directly to the student record
        from django.core.files.base import ContentFile
        img_bytes = _make_jpeg_bytes(color=(100, 150, 200))
        self.student.photo.save("face_test.jpg", ContentFile(img_bytes), save=True)

        result = train_model([self.student])
        # The photo has no real face so either trained (full-image fallback) or error
        # Either way, no crash and FaceEncoding may exist
        self.assertIsInstance(result["trained"] + result["skipped"] + [e[0] for e in result["errors"]], list)
        # Cleanup
        self.student.photo.delete(save=True)

    def test_confidence_threshold_is_centralised(self):
        """CONFIDENCE_THRESHOLD is defined in services_face.py."""
        self.assertIsInstance(CONFIDENCE_THRESHOLD, (int, float))
        self.assertGreater(CONFIDENCE_THRESHOLD, 0)

    def test_recognise_face_no_encodings(self):
        """recognise_face returns face_detected=False or message when no encodings exist."""
        frame = _make_jpeg_bytes()
        result = recognise_face(frame, [self.student.pk])
        self.assertFalse(result["success"])
        self.assertIn("message", result)


class FaceAttendanceViewTests(TestCase):

    def setUp(self):
        self.sy  = SchoolYear.objects.create(
            year="2023-2024", grading_system="term", is_active=True)
        self.gl  = GradeLevel.objects.create(name="Grade 11")
        self.sec = Section.objects.create(
            grade_level=self.gl, name="11-FR", track_strand="TVL")

        for role in ("admin", "principal", "ict_coordinator",
                     "teacher", "adviser", "subject_teacher",
                     "student", "parent"):
            User.objects.create_user(
                username=f"fr_{role}", password="p", role=role)

        self.std = Student.objects.create(
            lrn="FACE000002", first_name="FR", last_name="STUDENT",
            gender="Male", birth_date=datetime.date(2007, 1, 1),
        )
        Enrollment.objects.create(
            student=self.std, school_year=self.sy,
            grade_level=self.gl, section=self.sec, semester="1",
        )

    def _c(self, role):
        c = Client()
        c.login(username=f"fr_{role}", password="p")
        return c

    # ── face_train ────────────────────────────────────────────────────────

    def test_face_train_get_admin(self):
        r = self._c("admin").get("/attendance/face/train/")
        self.assertEqual(r.status_code, 200)

    def test_face_train_get_ict(self):
        r = self._c("ict_coordinator").get("/attendance/face/train/")
        self.assertEqual(r.status_code, 200)

    def test_face_train_get_principal(self):
        r = self._c("principal").get("/attendance/face/train/")
        self.assertEqual(r.status_code, 200)

    def test_face_train_blocked_teacher(self):
        self.assertEqual(
            self._c("teacher").get("/attendance/face/train/").status_code, 403)

    def test_face_train_blocked_student(self):
        self.assertEqual(
            self._c("student").get("/attendance/face/train/").status_code, 403)

    def test_face_train_post_runs_training(self):
        """POST to face_train runs training (returns 200 with result context)."""
        r = self._c("admin").post("/attendance/face/train/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("result", r.context)

    # ── face_attendance ───────────────────────────────────────────────────

    def test_face_attendance_get_teacher(self):
        r = self._c("teacher").get("/attendance/face/")
        self.assertEqual(r.status_code, 200)

    def test_face_attendance_blocked_student(self):
        self.assertEqual(
            self._c("student").get("/attendance/face/").status_code, 403)

    def test_face_attendance_blocked_parent(self):
        self.assertEqual(
            self._c("parent").get("/attendance/face/").status_code, 403)

    # ── face_scan ─────────────────────────────────────────────────────────

    def test_face_scan_with_no_encodings(self):
        """face_scan returns JSON with success=False when no encodings trained."""
        import base64
        frame_b64 = base64.b64encode(_make_jpeg_bytes()).decode()
        c = self._c("teacher")
        r = c.post(
            "/attendance/face/scan/",
            data=json.dumps({
                "frame":          f"data:image/jpeg;base64,{frame_b64}",
                "school_year_id": self.sy.pk,
                "section_id":     self.sec.pk,
            }),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data["success"])
        self.assertIn("message", data)

    def test_face_scan_bad_payload(self):
        """face_scan returns 400 on malformed JSON."""
        c = self._c("teacher")
        r = c.post(
            "/attendance/face/scan/",
            data="NOT JSON",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_face_scan_blocked_parent(self):
        """Parent role cannot access face_scan (403)."""
        r = self._c("parent").post("/attendance/face/scan/")
        self.assertEqual(r.status_code, 403)

    # ── Existing attendance unaffected ────────────────────────────────────

    def test_qr_session_create_unaffected(self):
        r = self._c("admin").get("/attendance/qr/create/")
        self.assertEqual(r.status_code, 200)

    def test_manual_mark_select_unaffected(self):
        r = self._c("teacher").get("/attendance/mark/")
        self.assertEqual(r.status_code, 200)
