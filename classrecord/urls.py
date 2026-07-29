from django.urls import path
from . import views

urlpatterns = [
    path("", views.class_record_select, name="class_record_select"),
    path(
        "<int:student_id>/<int:subject_id>/<int:school_year_id>/<int:quarter>/",
        views.class_record_detail,
        name="class_record_detail",
    ),
    path(
        "<int:student_id>/<int:subject_id>/<int:school_year_id>/<int:quarter>/add/",
        views.add_score_item,
        name="add_score_item",
    ),
    path(
        "<int:student_id>/<int:subject_id>/<int:school_year_id>/<int:quarter>/save/",
        views.save_to_grade,
        name="save_to_grade",
    ),
    path("item/<int:pk>/delete/", views.delete_score_item, name="delete_score_item"),

    # Official E-Class Record grid (roster-wide)
    path("ecr/", views.ecr_select, name="ecr_select"),
    path("ecr/<int:assignment_id>/<int:quarter>/", views.ecr_grid, name="ecr_grid"),
    path(
        "ecr/<int:assignment_id>/<int:quarter>/assessment/add/",
        views.ecr_add_assessment,
        name="ecr_add_assessment",
    ),
    path(
        "ecr/assessment/<int:pk>/delete/",
        views.ecr_delete_assessment,
        name="ecr_delete_assessment",
    ),

    # ECR Export — M-7Jul (Excel + PDF, Q1-C / Q2-A)
    path(
        "ecr/<int:assignment_id>/<int:quarter>/export/excel/",
        views.ecr_export_excel,
        name="ecr_export_excel",
    ),
    path(
        "ecr/<int:assignment_id>/<int:quarter>/export/pdf/",
        views.ecr_export_pdf,
        name="ecr_export_pdf",
    ),
]
