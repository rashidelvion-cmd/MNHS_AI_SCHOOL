from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):

    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('principal', 'Principal'),
        ('ict_coordinator', 'ICT Coordinator'),
        ('teacher', 'Teacher'),          # generic / backwards-compat
        ('adviser', 'Adviser Teacher'),
        ('subject_teacher', 'Subject Teacher'),
        ('student', 'Student'),
        ('parent', 'Parent'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    phone = models.CharField(max_length=15, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def is_staff_role(self):
        """True for all roles that have school-staff level access."""
        return self.role in (
            'admin', 'principal', 'ict_coordinator',
            'teacher', 'adviser', 'subject_teacher',
        )

    @property
    def can_generate_sf9_sf10(self):
        """Adviser, admin, principal and ICT Coordinator may generate SF9/SF10.
        Subject Teachers may NOT generate SF9/SF10 (client requirement)."""
        return self.role in ('admin', 'principal', 'ict_coordinator', 'teacher', 'adviser')

    @property
    def can_import_sf1(self):
        """Adviser and Subject Teacher may import SF1."""
        return self.role in ('admin', 'teacher', 'adviser', 'subject_teacher')

    def __str__(self):
        return self.username