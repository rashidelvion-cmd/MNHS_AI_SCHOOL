from django.urls import path
from . import views

urlpatterns = [
    path("sf9/", views.sf9_select, name="sf9_select"),
    path("sf9/<int:student_id>/<int:school_year_id>/", views.sf9_pdf, name="sf9_pdf"),

    # SF1 Import (upload -> preview -> confirm)
    path("sf1/import/", views.sf1_import, name="sf1_import"),
    path("sf1/import/<uuid:token>/preview/", views.sf1_import_preview, name="sf1_import_preview"),
    path("sf1/import/<uuid:token>/confirm/", views.sf1_import_confirm, name="sf1_import_confirm"),

    # SF1 Export (generate official SF1-SHS Excel)
    path("sf1/export/", views.sf1_export, name="sf1_export"),

    # SF1 PDF Print — D[063]
    path("sf1/pdf/", views.sf1_pdf_export, name="sf1_pdf_export"),

    # SF2 Export (generate official SF2-SHS Daily Attendance Report)
    path("sf2/export/", views.sf2_export, name="sf2_export"),

    # SF9 Export (generate the official SF9-SHS report card)
    path("sf9/export/", views.sf9_export, name="sf9_export"),

    # SF10 Export (generate the official SF10-SHS permanent record)
    path("sf10/export/", views.sf10_export, name="sf10_export"),

    # ID Maker — Module 11 (D[131-137])
    path("id/student/", views.id_maker_student, name="id_maker_student"),
    path("id/teacher/", views.id_maker_teacher, name="id_maker_teacher"),

    # Certificate Generator — Module 12 (D[138-145])
    path("certificates/", views.certificate_generate, name="certificate_generate"),
]
