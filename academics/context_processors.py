"""
Context processor for School Events & Notifications.

Makes `events_this_week` (integer) available in every template so that
the navbar badge can show upcoming events without modifying every view.

Client requirement (Messenger 7 Jul, R3):
    "All users must have notifications of school events and meetings"
"""

from datetime import date, timedelta


def events_badge(request):
    """
    Return the count of events in the next 7 days.
    Returns 0 for unauthenticated requests (login page, etc.).
    """
    if not request.user.is_authenticated:
        return {"events_this_week": 0}
    try:
        from academics.models import Event
        today = date.today()
        count = Event.objects.filter(
            event_date__gte=today,
            event_date__lte=today + timedelta(days=7),
        ).count()
        return {"events_this_week": count}
    except Exception:
        # Guard against missing table during first migration
        return {"events_this_week": 0}
