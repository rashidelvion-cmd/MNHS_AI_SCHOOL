from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Teacher

User = get_user_model()


class TeacherModelTests(TestCase):

    def test_str_returns_full_name(self):
        teacher = Teacher.objects.create(employee_id="T-001", first_name="Jane", last_name="Doe")
        self.assertEqual(str(teacher), "Jane Doe")

    def test_employee_id_must_be_unique(self):
        Teacher.objects.create(employee_id="T-001", first_name="Jane", last_name="Doe")
        with self.assertRaises(Exception):
            Teacher.objects.create(employee_id="T-001", first_name="John", last_name="Smith")


class TeacherViewAuthTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="staff", password="strongpass123", role="admin")
        self.teacher = Teacher.objects.create(employee_id="T-001", first_name="Jane", last_name="Doe")

    def test_list_requires_login(self):
        response = self.client.get(reverse("teacher_list"))
        self.assertEqual(response.status_code, 302)

    def test_delete_rejects_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("delete_teacher", args=[self.teacher.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Teacher.objects.filter(pk=self.teacher.pk).exists())

    def test_delete_via_post_removes_teacher(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("delete_teacher", args=[self.teacher.pk]))
        self.assertRedirects(response, reverse("teacher_list"))
        self.assertFalse(Teacher.objects.filter(pk=self.teacher.pk).exists())
