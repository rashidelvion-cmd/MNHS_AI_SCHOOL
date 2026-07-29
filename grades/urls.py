from django.urls import path
from . import views

urlpatterns = [
    path("", views.grade_list, name="grade_list"),
    path("add/", views.add_grade, name="add_grade"),

    # Ranking & Awards (additive)
    path("ranking/class/",   views.class_ranking_view,   name="class_ranking"),
    path("ranking/subject/", views.subject_ranking_view, name="subject_ranking"),
    path("ranking/awards/",  views.awards_list_view,     name="awards_list"),

    # Grade Locking — D[094]
    path("<int:pk>/lock/",   views.lock_grade,   name="lock_grade"),
    path("<int:pk>/unlock/", views.unlock_grade, name="unlock_grade"),

    # Grade Verification — D[095]
    path("<int:pk>/verify/",   views.verify_grade,   name="verify_grade"),
    path("<int:pk>/unverify/", views.unverify_grade, name="unverify_grade"),
]