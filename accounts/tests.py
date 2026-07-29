from django.test import TestCase
from django.urls import reverse

from .models import User


class LoginViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="strongpass123")

    def test_login_page_loads(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_valid_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "strongpass123"},
        )
        self.assertRedirects(response, reverse("dashboard"))

    def test_invalid_login_shows_error(self):
        response = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "wrongpass"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid Username or Password")

    def test_logout_redirects_to_login(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
