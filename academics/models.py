from django.db import models
from teachers.models import Teacher


class SchoolYear(models.Model):

    GRADING_SYSTEM_CHOICES = [
        ("quarter", "Quarter (Q1–Q4)"),
        ("term", "Term (1–3)"),
    ]

    year = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    grading_system = models.CharField(
        max_length=10,
        choices=GRADING_SYSTEM_CHOICES,
        default="quarter",
        help_text="Whether this school year is graded by 4 quarters or 3 terms.",
    )

    @property
    def period_count(self):
        return 3 if self.grading_system == "term" else 4

    def period_label(self, period_number):
        return f"Term {period_number}" if self.grading_system == "term" else f"Q{period_number}"

    def __str__(self):
        return self.year


class GradeLevel(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Section(models.Model):
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=50)

    # SF1-SHS header fields (Category 2 — export fidelity). Optional so
    # existing sections and forms are unaffected.
    track_strand = models.CharField(
        "Track and Strand",
        max_length=100,
        blank=True,
        default="",
        help_text="e.g. Academic - STEM, TVL - ICT (printed on SF1/SF9/SF10 SHS forms)",
    )
    course = models.CharField(
        "Course (for TVL only)",
        max_length=100,
        blank=True,
        default="",
    )

    def __str__(self):
        return f"{self.grade_level} - {self.name}"


class Subject(models.Model):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.code} - {self.name}"


class SubjectAssignment(models.Model):
    SEMESTER_CHOICES = [
        ("1", "1st Semester"),
        ("2", "2nd Semester"),
    ]

    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.CASCADE
    )

    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE
    )

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE
    )

    # Which semester this subject is taken in, within the school year.
    # Nullable so existing assignments and the 3-term grading logic are
    # unaffected; used only to place subjects into the correct SF10
    # semester block. Grading itself is unchanged.
    semester = models.CharField(
        max_length=1,
        choices=SEMESTER_CHOICES,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.subject} - {self.section} - {self.teacher}"

class Event(models.Model):
    """
    A school event or meeting visible to all users.

    Client requirement (Messenger 7 Jul):
        R1 — students want viewing of grades and school events
        R2 — Parent Dashboard: Notification of School Events and Meetings
        R3 — All users must have notifications of school events and meetings

    Fields derived strictly from R1-R3. No per-user read tracking,
    no section/school-year scoping, no attachments — none specified.
    """

    title       = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    event_date  = models.DateField()
    event_time  = models.TimeField(null=True, blank=True)
    created_by  = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_created",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["event_date", "event_time"]

    def __str__(self):
        return self.title
