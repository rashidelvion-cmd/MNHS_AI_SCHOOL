from django.db import models
from students.models import Student
from academics.models import SchoolYear, GradeLevel, Section


class Enrollment(models.Model):
    SEMESTER_CHOICES = [
        ("1", "1st Semester"),
        ("2", "2nd Semester"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE)
    grade_level = models.ForeignKey(GradeLevel, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    date_enrolled = models.DateField(auto_now_add=True)

    # SF1-SHS is issued per semester (Category 2 — export fidelity).
    # Nullable so existing enrollments are unaffected.
    semester = models.CharField(
        max_length=1,
        choices=SEMESTER_CHOICES,
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "school_year"],
                name="unique_enrollment_per_student_per_year",
            )
        ]
        ordering = ["-date_enrolled"]

    def __str__(self):
        return f"{self.student} - {self.school_year}"