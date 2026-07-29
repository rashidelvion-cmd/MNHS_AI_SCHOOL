"""
academics/views.py

School Events & Notifications views.
Client requirement (Messenger 7 Jul):
    R1 — students: viewing of grades and school events
    R2 — Parent Dashboard: Notification of School Events and Meetings
    R3 — All users must have notifications of school events and meetings

Permissions:
    View  — all 8 authenticated roles
    Create / Edit / Delete — admin, principal, ict_coordinator only
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from .models import Event

EVENT_MANAGE_ROLES = ("admin", "principal", "ict_coordinator")


@login_required
def event_list(request):
    """All authenticated users can view events (R3)."""
    from datetime import date
    today = date.today()
    upcoming = Event.objects.filter(event_date__gte=today).order_by("event_date", "event_time")
    past     = Event.objects.filter(event_date__lt=today).order_by("-event_date", "-event_time")
    can_manage = request.user.role in EVENT_MANAGE_ROLES or request.user.is_superuser
    return render(request, "academics/event_list.html", {
        "upcoming":    upcoming,
        "past":        past,
        "can_manage":  can_manage,
    })


@role_required(*EVENT_MANAGE_ROLES)
def event_create(request):
    """admin / principal / ict_coordinator can create events."""
    if request.method == "POST":
        title      = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        event_date = request.POST.get("event_date", "").strip()
        event_time = request.POST.get("event_time", "").strip() or None

        if not title or not event_date:
            messages.warning(request, "Title and date are required.")
            return render(request, "academics/event_form.html", {
                "action": "Create",
                "post": request.POST,
            })

        Event.objects.create(
            title=title,
            description=description,
            event_date=event_date,
            event_time=event_time,
            created_by=request.user,
        )
        messages.success(request, f"Event \"{title}\" created successfully.")
        return redirect("event_list")

    return render(request, "academics/event_form.html", {"action": "Create"})


@role_required(*EVENT_MANAGE_ROLES)
def event_edit(request, pk):
    """admin / principal / ict_coordinator can edit events."""
    event = get_object_or_404(Event, pk=pk)

    if request.method == "POST":
        title       = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        event_date  = request.POST.get("event_date", "").strip()
        event_time  = request.POST.get("event_time", "").strip() or None

        if not title or not event_date:
            messages.warning(request, "Title and date are required.")
            return render(request, "academics/event_form.html", {
                "action": "Edit", "event": event, "post": request.POST,
            })

        event.title       = title
        event.description = description
        event.event_date  = event_date
        event.event_time  = event_time
        event.save()
        messages.success(request, f"Event \"{title}\" updated.")
        return redirect("event_list")

    return render(request, "academics/event_form.html", {
        "action": "Edit", "event": event,
    })


@role_required(*EVENT_MANAGE_ROLES)
def event_delete(request, pk):
    """admin / principal / ict_coordinator can delete events."""
    event = get_object_or_404(Event, pk=pk)
    if request.method == "POST":
        title = event.title
        event.delete()
        messages.success(request, f"Event \"{title}\" deleted.")
    return redirect("event_list")
