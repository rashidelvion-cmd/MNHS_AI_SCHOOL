from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from students.models import Student
from academics.models import Subject, SchoolYear

GRADE_VALIDATORS = [MinValueValidator(0), MaxValueValidator(100)]


class Grade(models.Model):

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE)

    # Periods 1-3 apply to both grading systems. Period 4 only applies
    # when school_year.grading_system == "quarter" — left blank for
    # term-based (3-term) school years.
    first_quarter = models.DecimalField(max_digits=5, decimal_places=2, validators=GRADE_VALIDATORS, null=True, blank=True)
    second_quarter = models.DecimalField(max_digits=5, decimal_places=2, validators=GRADE_VALIDATORS, null=True, blank=True)
    third_quarter = models.DecimalField(max_digits=5, decimal_places=2, validators=GRADE_VALIDATORS, null=True, blank=True)
    fourth_quarter = models.DecimalField(max_digits=5, decimal_places=2, validators=GRADE_VALIDATORS, null=True, blank=True)

    final_grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        validators=GRADE_VALIDATORS,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "school_year"],
                name="unique_grade_per_student_per_subject_per_year",
            )
        ]

    # Grade Locking — D[094]
    # When True, Grade.save() raises ValidationError for any field change.
    # Lock: admin + principal (Q1).  Unlock: admin only (Q2).
    is_locked = models.BooleanField(
        default=False,
        help_text="When True, this grade record cannot be modified.",
    )

    # Grade Verification — D[095]
    # When True, an authorized user has reviewed and approved this record.
    # Verify: admin + principal (Q1).  Unverify: admin only (Q2).
    # Q3-A: editing a verified grade resets is_verified to False automatically.
    # Q4-A: locking and verification are independent.
    is_verified = models.BooleanField(
        default=False,
        help_text="When True, this grade has been verified by an authorized user.",
    )

    def period_values(self):
        """The quarter/term values that actually apply to this school year's grading system, in order."""
        all_periods = [self.first_quarter, self.second_quarter, self.third_quarter, self.fourth_quarter]
        return all_periods[: self.school_year.period_count]

    def save(self, *args, **kwargs):
        # Grade Locking check — D[094]
        # Only applies to existing records (pk already set).
        # New grade creation (first save, no pk yet) is never blocked.
        if self.pk:
            locked = Grade.objects.filter(pk=self.pk).values("is_locked").first()
            if locked and locked["is_locked"]:
                from django.core.exceptions import ValidationError
                raise ValidationError(
                    "This grade record is locked and cannot be modified. "
                    "Contact an administrator to unlock it."
                )

        # Grade Verification — Q3-A: reset is_verified on any edit
        # Only applies to existing records (pk already set).
        # Updating is_verified itself (via .update()) bypasses save(), so this
        # reset only fires when grade values actually change.
        if self.pk:
            self.is_verified = False

        # DepEd rule: Final Grade = average of the applicable periods
        # (4 quarters, or 3 terms depending on the school year's grading system).
        periods = self.period_values()
        if periods and all(p is not None for p in periods):
            self.final_grade = round(sum(periods) / len(periods), 2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.subject}"