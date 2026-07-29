from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("grades", "0002_alter_grade_final_grade_alter_grade_first_quarter_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="grade",
            name="first_quarter",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
        migrations.AlterField(
            model_name="grade",
            name="second_quarter",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
        migrations.AlterField(
            model_name="grade",
            name="third_quarter",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
        migrations.AlterField(
            model_name="grade",
            name="fourth_quarter",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
    ]
