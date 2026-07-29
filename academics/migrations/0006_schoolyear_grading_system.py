from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0005_subjectassignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolyear",
            name="grading_system",
            field=models.CharField(
                choices=[("quarter", "Quarter (Q1–Q4)"), ("term", "Term (1–3)")],
                default="quarter",
                help_text="Whether this school year is graded by 4 quarters or 3 terms.",
                max_length=10,
            ),
        ),
    ]
