from django.conf import settings
from django.db import models
from academics.models import SchoolYear, GradeLevel, Section


class Student(models.Model):
    lrn = models.CharField(max_length=20, unique=True)

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)

    gender = models.CharField(
        max_length=10,
        choices=[
            ("Male", "Male"),
            ("Female", "Female"),
        ],
    )

    birth_date = models.DateField()

    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    # Login account this student uses to see their own records (role="student").
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
    )

    # Parent/guardian login account(s) allowed to view this student's records (role="parent").
    guardians = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="children",
    )

    # ==========================================================
    # SF1 (School Register) learner fields — Category 1 freeze.
    # All optional/blank so existing records and forms are
    # unaffected (additive, backward compatible).
    # ==========================================================

    # Official DepEd name format: "Last Name, First Name, Name Extension, Middle Name"
    name_extension = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="e.g. Jr., III (SF1 name format)",
    )

    religious_affiliation = models.CharField(max_length=100, blank=True, default="")

    # SF1 COMPLETE ADDRESS block (four official sub-columns)
    house_street = models.CharField(
        "House No./Street/Sitio/Purok",
        max_length=150,
        blank=True,
        default="",
    )
    barangay = models.CharField(max_length=100, blank=True, default="")
    municipality = models.CharField(
        "Municipality/City",
        max_length=100,
        blank=True,
        default="",
    )
    province = models.CharField(max_length=100, blank=True, default="")

    # SF1 PARENTS block
    father_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Last Name, First Name, Name Extension, Middle Name",
    )
    mother_maiden_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Last Name, First Name, Name Extension, Middle Name",
    )

    # SF1 GUARDIAN block (if learner is not living with parents)
    guardian_name = models.CharField(max_length=150, blank=True, default="")
    guardian_relationship = models.CharField(max_length=100, blank=True, default="")

    contact_number = models.CharField(
        "Contact Number of Parent/Guardian",
        max_length=30,
        blank=True,
        default="",
    )

    # SF1 REMARKS legend codes: T/O, T/I, CCT, B/A, LWE, ACL (free text to
    # allow the combinations and annotations the official form permits).
    remarks_code = models.CharField(
        "Remarks",
        max_length=100,
        blank=True,
        default="",
        help_text="SF1 legend codes, e.g. T/O, T/I, CCT, B/A, LWE, ACL",
    )

    # Student photo — D[056] Upload Student Photo
    # Optional: existing students have no photo (null=True, blank=True).
    # Used by ID Maker and is a prerequisite for Face Recognition (final phase).
    photo = models.ImageField(
        upload_to="student_photos/",
        blank=True,
        null=True,
        help_text="Student photo — used for ID card and face recognition.",
    )

    # Medical Information — D[055]
    # All three fields are optional (blank=True).
    # Visible to authorized staff only (Q3-B).
    # Not shown on student list page (Q2-A).
    medical_condition = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Known illness, disability, or special medical condition.",
    )
    allergies = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Food, medicine, or other allergies.",
    )
    blood_type = models.CharField(
        max_length=5,
        blank=True,
        default="",
        help_text="e.g. O+, A-, B+, AB+",
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"