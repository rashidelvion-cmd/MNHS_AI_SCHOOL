from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("dashboard.urls")),
    path("students/", include("students.urls")),
    path("enrollment/", include("enrollment.urls")),
    path("attendance/", include("attendance.urls")),
    path("grades/", include("grades.urls")),
    path("classrecord/", include("classrecord.urls")),
    path("reports/", include("reports.urls")),
    path("teachers/", include("teachers.urls")),
    path("events/", include("academics.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)