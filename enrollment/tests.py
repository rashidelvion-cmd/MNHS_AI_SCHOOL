from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from academics.models import GradeLevel, SchoolYear, Section
from students.models import Student
from .models import Enrollment

User = get_user_model()


class EnrollmentModelTests(TestCase):

    def setUp(self):
        self.student = Student.objects.create(
            lrn="123456789012",
            first_name="Juan",
            last_name="Cruz",
            gender="Male",
            birth_date="2012-05-01",
        )
        self.school_year = SchoolYear.objects.create(year="2025-2026")
        self.grade_level = GradeLevel.objects.create(name="Grade 7")
        self.section = Section.objects.create(grade_level=self.grade_level, name="Diamond")

    def test_duplicate_enrollment_same_year_rejected(self):
        Enrollment.objects.create(
            student=self.student,
            school_year=self.school_year,
            grade_level=self.grade_level,
            section=self.section,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Enrollment.objects.create(
                    student=self.student,
                    school_year=self.school_year,
                    grade_level=self.grade_level,
                    section=self.section,
                )


class EnrollmentViewAuthTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="staff", password="strongpass123")

    def test_list_requires_login(self):
        response = self.client.get(reverse("enrollment_list"))
        self.assertEqual(response.status_code, 302)

    def test_list_accessible_when_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("enrollment_list"))
        self.assertEqual(response.status_code, 200)
