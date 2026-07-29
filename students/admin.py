from django.contrib import admin
from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):

    list_display = (
        "lrn",
        "first_name",
        "last_name",
        "grade_level",
        "section",
        "gender",
        "user",
    )

    search_fields = (
        "lrn",
        "first_name",
        "last_name",
        "user__username",
    )

    list_filter = (
        "grade_level",
        "section",
        "gender",
    )

    autocomplete_fields = ("user",)
    filter_horizontal = ("guardians",)