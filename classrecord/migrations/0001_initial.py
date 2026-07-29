import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("academics", "0005_subjectassignment"),
        ("students", "0003_student_user_student_guardians"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubjectWeighting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "written_work_weight",
                    models.PositiveSmallIntegerField(
                        default=30,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                (
                    "performance_task_weight",
                    models.PositiveSmallIntegerField(
                        default=50,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                (
                    "quarterly_assessment_weight",
                    models.PositiveSmallIntegerField(
                        default=20,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                (
                    "subject",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="academics.subject",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ScoreItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "quarter",
                    models.PositiveSmallIntegerField(
                        choices=[(1, "1st Quarter"), (2, "2nd Quarter"), (3, "3rd Quarter"), (4, "4th Quarter")]
                    ),
                ),
                (
                    "component",
                    models.CharField(
                        choices=[("WW", "Written Work"), ("PT", "Performance Task"), ("QA", "Quarterly Assessment")],
                        max_length=2,
                    ),
                ),
                ("label", models.CharField(help_text="e.g. Quiz 1, Seatwork 2, Q3 Exam", max_length=100)),
                ("raw_score", models.DecimalField(decimal_places=2, max_digits=6)),
                ("highest_score", models.DecimalField(decimal_places=2, max_digits=6)),
                (
                    "school_year",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.schoolyear"),
                ),
                (
                    "student",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="students.student"),
                ),
                (
                    "subject",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.subject"),
                ),
            ],
            options={
                "ordering": ["quarter", "component", "id"],
            },
        ),
    ]
