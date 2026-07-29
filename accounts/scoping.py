STAFF_ROLES = (
    "admin", "principal", "ict_coordinator",
    "teacher", "adviser", "subject_teacher",
)


def scope_to_visible_students(user, queryset, student_lookup="student"):
    """
    Restrict `queryset` to the students `user` is allowed to see.

    - admin / principal / teacher (or superuser): see everything, unchanged.
    - student: only rows tied to their own Student record.
    - parent: only rows tied to a Student they are listed as a guardian of.
    - anything else: nothing.

    `student_lookup` is the field path from `queryset`'s model to the
    Student it belongs to. Use "" when the queryset IS the Student model
    itself (e.g. Student.objects.all()), or e.g. "student" when the model
    has a `student` ForeignKey (e.g. Grade, Attendance, Enrollment).
    """

    if getattr(user, "is_superuser", False) or getattr(user, "role", None) in STAFF_ROLES:
        return queryset

    prefix = f"{student_lookup}__" if student_lookup else ""

    if user.role == "student":
        return queryset.filter(**{f"{prefix}user": user})

    if user.role == "parent":
        return queryset.filter(**{f"{prefix}guardians": user})

    return queryset.none()
