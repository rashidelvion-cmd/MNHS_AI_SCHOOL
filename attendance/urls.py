from django.urls import path
from . import views

urlpatterns = [
    path("", views.attendance_list, name="attendance_list"),
    path("add/", views.add_attendance, name="add_attendance"),

    # Bulk marking (SF2 workflow)
    path("mark/", views.attendance_mark_select, name="attendance_mark_select"),
    path(
        "mark/<int:school_year_id>/<int:section_id>/<str:date>/",
        views.attendance_mark_sheet,
        name="attendance_mark_sheet",
    ),

    # QR Attendance — Module 13 (D[146-149])
    path("qr/create/",   views.qr_session_create, name="qr_session_create"),
    path("qr/sessions/", views.qr_session_list,   name="qr_session_list"),
    path("qr/scan/<uuid:token>/", views.qr_scan,  name="qr_scan"),

    # Face Recognition Attendance — M-4Jul (OpenCV LBPH, Q1-A)
    path("face/train/",      views.face_train,      name="face_train"),
    path("face/",            views.face_attendance, name="face_attendance"),
    path("face/scan/",       views.face_scan,       name="face_scan"),
]