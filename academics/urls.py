from django.urls import path
from . import views

urlpatterns = [
    # School Events & Notifications — R1/R2/R3 (Messenger 7 Jul)
    path("",              views.event_list,   name="event_list"),
    path("create/",       views.event_create, name="event_create"),
    path("<int:pk>/edit/",   views.event_edit,   name="event_edit"),
    path("<int:pk>/delete/", views.event_delete, name="event_delete"),
]
