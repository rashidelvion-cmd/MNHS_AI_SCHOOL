from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    """
    Restrict a view to users whose `role` is in `allowed_roles`.

    Usage:
        @role_required("admin", "principal", "teacher")
        def add_student(request):
            ...

    Must be combined with @login_required (or used after it) since it
    assumes request.user is authenticated.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.role not in allowed_roles and not request.user.is_superuser:
                raise PermissionDenied(
                    "You do not have permission to perform this action."
                )
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
