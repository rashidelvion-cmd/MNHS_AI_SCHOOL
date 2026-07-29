from django.urls import path
from . import views
from django.contrib.auth.decorators import login_required

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
]