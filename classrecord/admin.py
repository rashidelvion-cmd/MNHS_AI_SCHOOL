from django.contrib import admin
from .models import SubjectWeighting, ScoreItem


@admin.register(SubjectWeighting)
class SubjectWeightingAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "written_work_weight",
        "performance_task_weight",
        "quarterly_assessment_weight",
    )


@admin.register(ScoreItem)
class ScoreItemAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "subject",
        "school_year",
        "quarter",
        "component",
        "label",
        "raw_score",
        "highest_score",
    )
    list_filter = ("school_year", "quarter", "component", "subject")
    search_fields = ("student__first_name", "student__last_name", "label")
