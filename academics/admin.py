from django.contrib import admin
from .models import (
    SchoolYear,
    GradeLevel,
    Section,
    Subject,
    SubjectAssignment,
)


admin.site.register(SchoolYear)
admin.site.register(GradeLevel)
admin.site.register(Section)
admin.site.register(Subject)


@admin.register(SubjectAssignment)
class SubjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ("school_year", "section", "subject", "teacher", "semester")
    list_filter = ("school_year", "semester", "section")
    list_editable = ("semester",)
    search_fields = ("subject__name", "subject__code", "section__name")