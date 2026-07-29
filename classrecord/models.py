from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from academics.models import Subject, SchoolYear
from students.models import Student

QUARTER_CHOICES = [
    (1, "1st Quarter"),
    (2, "2nd Quarter"),
    (3, "3rd Quarter"),
    (4, "4th Quarter"),
]

COMPONENT_CHOICES = [
    ("WW", "Written Work"),
    ("PT", "Performance Task"),
    ("QA", "Quarterly Assessment"),
]

# DepEd default weight sets by subject type (Languages/AP/EsP, Math/Science, MAPEH/EPP-TLE).
# Used when a subject has no explicit SubjectWeighting configured.
DEFAULT_WEIGHTS = {"WW": 30, "PT": 50, "QA": 20}


class SubjectWeighting(models.Model):
    """
    DepEd weighting (must total 100%) for how Written Work, Performance
    Task, and Quarterly Assessment combine into the Quarterly Grade.
    Configurable per subject since the official weights differ by
    learning area (e.g. Languages vs Math/Science vs MAPEH).
    """

    subject = models.OneToOneField(Subject, on_delete=models.CASCADE)

    written_work_weight = models.PositiveSmallIntegerField(
        default=DEFAULT_WEIGHTS["WW"],
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    performance_task_weight = models.PositiveSmallIntegerField(
        default=DEFAULT_WEIGHTS["PT"],
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    quarterly_assessment_weight = models.PositiveSmallIntegerField(
        default=DEFAULT_WEIGHTS["QA"],
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    def clean(self):
        from django.core.exceptions import ValidationError

        total = (
            self.written_work_weight
            + self.performance_task_weight
            + self.quarterly_assessment_weight
        )
        if total != 100:
            raise ValidationError(
                f"Written Work + Performance Task + Quarterly Assessment weights must total 100% (currently {total}%)."
            )

    def __str__(self):
        return f"{self.subject} weights ({self.written_work_weight}/{self.performance_task_weight}/{self.quarterly_assessment_weight})"


class ScoreItem(models.Model):
    """
    A single graded item (a quiz, a seatwork, a performance task, the
    quarterly exam, etc.) entered under the Written Work / Performance
    Task / Quarterly Assessment component for one student, one subject,
    one school year, one quarter.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE)
    quarter = models.PositiveSmallIntegerField(choices=QUARTER_CHOICES)
    component = models.CharField(max_length=2, choices=COMPONENT_CHOICES)

    label = models.CharField(max_length=100, help_text="e.g. Quiz 1, Seatwork 2, Q3 Exam")
    raw_score = models.DecimalField(max_digits=6, decimal_places=2)
    highest_score = models.DecimalField(max_digits=6, decimal_places=2)

    # E-Class Record grid link (additive; legacy free-form items keep this
    # empty). When set, label/highest_score mirror the Assessment so every
    # existing computation keeps working unchanged.
    assessment = models.ForeignKey(
        "classrecord.Assessment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="score_items",
    )

    class Meta:
        ordering = ["quarter", "component", "id"]

    def __str__(self):
        return f"{self.student} - {self.subject} - Q{self.quarter} - {self.get_component_display()} - {self.label}"


class Assessment(models.Model):
    """
    One graded column of the official E-Class Record, defined once for the
    whole class: e.g. "WW1 - Quiz 1 (HPS 20)" for a SubjectAssignment
    (teacher + subject + section + school year) in one quarter/term.

    Additive: the legacy free-form ScoreItem flow (no assessment link)
    remains fully valid.
    """

    subject_assignment = models.ForeignKey(
        "academics.SubjectAssignment",
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    quarter = models.PositiveSmallIntegerField(choices=QUARTER_CHOICES)
    component = models.CharField(max_length=2, choices=COMPONENT_CHOICES)
    label = models.CharField(max_length=100, help_text="e.g. Quiz 1, PT 2, Term Exam")
    highest_score = models.DecimalField(max_digits=6, decimal_places=2)
    order = models.PositiveSmallIntegerField(default=0)

    # Learning Competencies — D[082]
    # Optional free-text (Q2-A). Identifies the skill/topic the assessment covers.
    competency = models.CharField(
        max_length=300,
        blank=True,
        default="",
        help_text="Learning competency this assessment covers, e.g. Identifies the domain and range of a function.",
    )

    class Meta:
        ordering = ["quarter", "component", "order", "id"]

    def __str__(self):
        return (
            f"{self.subject_assignment} - Q{self.quarter} - "
            f"{self.component} - {self.label} (HPS {self.highest_score})"
        )
