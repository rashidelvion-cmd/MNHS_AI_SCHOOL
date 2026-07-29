from django.db import models
from students.models import Student


class Attendance(models.Model):

    STATUS_CHOICES = [
        ("Present", "Present"),
        ("Absent", "Absent"),
        ("Late", "Late"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE
    )

    date = models.DateField(db_index=True)

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES
    )

    remarks = models.CharField(
        max_length=200,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "date"],
                name="unique_attendance_per_student_per_day",
            )
        ]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student} - {self.date} - {self.status}"

import uuid


class QRAttendanceSession(models.Model):
    """
    A staff-created attendance session tied to a school year, section, and
    date.  The session token is encoded in a QR code displayed by staff.
    Students scan that QR on their own authenticated mobile devices.

    Approved workflow (D[146-149]):
        Staff creates session → QR displayed on staff screen
        Student scans QR with own phone (authenticated)
        System records Attendance(student, date=session.date, status="Present")
        SF2 reads the Attendance record automatically (no exporter change)

    Approved decisions:
        D1-β  date = staff-selected at session creation time
        D2-α  scan records status = "Present"
    """

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    school_year = models.ForeignKey(
        "academics.SchoolYear",
        on_delete=models.CASCADE,
        related_name="qr_sessions",
    )
    section = models.ForeignKey(
        "academics.Section",
        on_delete=models.CASCADE,
        related_name="qr_sessions",
    )
    date = models.DateField(
        help_text="Attendance date selected by staff when creating this session.",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="qr_sessions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"QR Session – {self.section} | {self.date} | {self.school_year}"
        )


# ---------------------------------------------------------------------------
# Face Recognition Attendance — M-4Jul (Messenger)
# Client: "Face Recognition on the attendance part" / "Mobile Cam only"
# Path: OpenCV LBPH (Q1-A) — no new dependencies required
# ---------------------------------------------------------------------------

class FaceEncoding(models.Model):
    """
    Stores the per-student LBPH training data extracted from their reference photo.
    One record per student. Rebuilt by the Train Model action whenever photos change.

    Fields:
        student     — the student this encoding belongs to (one-to-one)
        encoding    — pickled LBPH histogram data (binary blob)
        trained_at  — auto-updated on every retrain
        source_photo — the photo filename used for training (audit)
    """
    student = models.OneToOneField(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="face_encoding",
    )
    encoding = models.BinaryField(
        help_text="Pickled LBPH face histogram for this student.",
    )
    trained_at = models.DateTimeField(auto_now=True)
    source_photo = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Relative path of the photo used to generate this encoding.",
    )

    def __str__(self):
        return f"FaceEncoding — {self.student}"
