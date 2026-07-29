from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Student

User = get_user_model()


class StudentModelTests(TestCase):

    def test_str_returns_full_name(self):
        student = Student.objects.create(
            lrn="123456789012",
            first_name="Juan",
            last_name="Cruz",
            gender="Male",
            birth_date="2012-05-01",
        )
        self.assertEqual(str(student), "Juan Cruz")

    def test_lrn_must_be_unique(self):
        Student.objects.create(
            lrn="123456789012",
            first_name="Juan",
            last_name="Cruz",
            gender="Male",
            birth_date="2012-05-01",
        )
        with self.assertRaises(Exception):
            Student.objects.create(
                lrn="123456789012",
                first_name="Maria",
                last_name="Santos",
                gender="Female",
                birth_date="2012-06-01",
            )


class StudentViewAuthTests(TestCase):
    """CRUD views must require login, and delete must reject GET."""

    def setUp(self):
        self.user = User.objects.create_user(username="staff", password="strongpass123", role="admin")
        self.student = Student.objects.create(
            lrn="123456789012",
            first_name="Juan",
            last_name="Cruz",
            gender="Male",
            birth_date="2012-05-01",
        )

    def test_list_requires_login(self):
        response = self.client.get(reverse("student_list"))
        self.assertEqual(response.status_code, 302)

    def test_list_accessible_when_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("student_list"))
        self.assertEqual(response.status_code, 200)

    def test_delete_requires_login(self):
        response = self.client.post(reverse("delete_student", args=[self.student.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    def test_delete_rejects_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("delete_student", args=[self.student.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    def test_delete_via_post_removes_student(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("delete_student", args=[self.student.pk]))
        self.assertRedirects(response, reverse("student_list"))
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())


# ---------------------------------------------------------------------------
# Student Photo Upload tests — D[056]
# ---------------------------------------------------------------------------

import io
import datetime
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()


def _make_image_file(name="photo.jpg", color=(255, 0, 0)):
    """Return a minimal valid JPEG as a SimpleUploadedFile."""
    from PIL import Image as PILImage
    buf = io.BytesIO()
    img = PILImage.new("RGB", (100, 100), color=color)
    img.save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


class StudentPhotoFieldTests(TestCase):
    """Model-level tests — no view involved."""

    def test_photo_field_nullable(self):
        """Student can be created without a photo (backward compatibility)."""
        s = Student.objects.create(
            lrn="000001", first_name="X", last_name="Y",
            gender="Male", birth_date=datetime.date(2007, 1, 1),
        )
        self.assertIsNone(s.photo.name)

    def test_photo_field_exists_on_model(self):
        """Student model has a photo ImageField."""
        from django.db.models import ImageField
        field = Student._meta.get_field("photo")
        self.assertIsInstance(field, ImageField)

    def test_photo_upload_to(self):
        """Photo field uses student_photos/ upload path."""
        field = Student._meta.get_field("photo")
        self.assertEqual(field.upload_to, "student_photos/")


class StudentPhotoViewTests(TestCase):
    """View-level tests for upload, list, and edit."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="adv_photo", password="p", role="adviser")
        self.student = Student.objects.create(
            lrn="000002", first_name="JUAN", last_name="DELA CRUZ",
            gender="Male", birth_date=datetime.date(2007, 1, 1),
        )

    def _client(self):
        c = Client()
        c.login(username="adv_photo", password="p")
        return c

    def test_add_student_form_renders(self):
        """Add-student page returns 200 and contains enctype multipart."""
        r = self._client().get("/students/add/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "multipart/form-data")

    def test_edit_student_form_renders(self):
        """Edit-student page returns 200 and contains enctype multipart."""
        r = self._client().get(f"/students/edit/{self.student.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "multipart/form-data")

    def test_photo_upload_via_edit_view(self):
        """POST with a valid JPEG saves the photo to the student record."""
        img = _make_image_file("test.jpg")
        r = self._client().post(
            f"/students/edit/{self.student.pk}/",
            {
                "lrn":        "000002",
                "first_name": "JUAN",
                "last_name":  "DELA CRUZ",
                "gender":     "Male",
                "birth_date": "2007-01-01",
                "photo":      img,
            },
        )
        # Should redirect back to student list
        self.assertIn(r.status_code, [301, 302])
        self.student.refresh_from_db()
        self.assertTrue(bool(self.student.photo))
        self.assertIn("student_photos/", self.student.photo.name)

    def test_student_list_renders_with_photo(self):
        """Student list page renders without error when a student has a photo."""
        # Give the student a photo (bypass form validation)
        img = _make_image_file("list_test.jpg")
        self.student.photo.save("list_test.jpg", img, save=True)
        r = self._client().get("/students/")
        self.assertEqual(r.status_code, 200)

    def test_student_list_renders_without_photo(self):
        """Student list page renders without error when student has no photo."""
        r = self._client().get("/students/")
        self.assertEqual(r.status_code, 200)

    def test_edit_form_rejects_non_image(self):
        """Uploading a text file is rejected as invalid."""
        bad_file = SimpleUploadedFile(
            "not_an_image.txt", b"hello world", content_type="text/plain")
        r = self._client().post(
            f"/students/edit/{self.student.pk}/",
            {
                "lrn":        "000002",
                "first_name": "JUAN",
                "last_name":  "DELA CRUZ",
                "gender":     "Male",
                "birth_date": "2007-01-01",
                "photo":      bad_file,
            },
        )
        # Form is invalid — re-renders the form page (200) not a redirect
        self.assertEqual(r.status_code, 200)
        self.student.refresh_from_db()
        # Photo must not be saved
        self.assertFalse(bool(self.student.photo))

    def test_student_list_regression(self):
        """Existing student_list view still works after photo field addition."""
        r = self._client().get("/students/")
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# Student Search tests — D[064]
# ---------------------------------------------------------------------------

class StudentSearchTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(
            username="srch_staff", password="p", role="adviser")
        # Three students with distinct names and LRNs
        self.s1 = Student.objects.create(
            lrn="100000000001", first_name="MARIA",   last_name="SANTOS",
            gender="Female", birth_date=datetime.date(2007, 1, 1))
        self.s2 = Student.objects.create(
            lrn="100000000002", first_name="JUAN",    last_name="DELA CRUZ",
            gender="Male",   birth_date=datetime.date(2007, 2, 1))
        self.s3 = Student.objects.create(
            lrn="100000000003", first_name="ANTONIO", last_name="REYES",
            gender="Male",   birth_date=datetime.date(2007, 3, 1))

    def _get(self, q=""):
        c = Client()
        c.login(username="srch_staff", password="p")
        url = "/students/" + (f"?q={q}" if q else "")
        return c.get(url)

    def test_search_by_lrn(self):
        """Searching by exact LRN returns only that student."""
        r = self._get("100000000001")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        self.assertIn("MARIA", content)
        self.assertNotIn("JUAN", content)
        self.assertNotIn("ANTONIO", content)

    def test_search_by_last_name(self):
        """Searching by last name returns matching students."""
        r = self._get("SANTOS")
        content = r.content.decode()
        self.assertIn("MARIA", content)
        self.assertNotIn("DELA CRUZ", content)

    def test_search_by_first_name(self):
        """Searching by first name returns matching students."""
        r = self._get("JUAN")
        content = r.content.decode()
        self.assertIn("JUAN", content)
        self.assertNotIn("MARIA", content)
        self.assertNotIn("ANTONIO", content)

    def test_search_case_insensitive(self):
        """Lowercase query matches uppercase stored name."""
        r = self._get("santos")
        content = r.content.decode()
        self.assertIn("MARIA", content)

    def test_search_partial_match(self):
        """Partial name match returns matching students."""
        r = self._get("cruz")
        content = r.content.decode()
        self.assertIn("DELA CRUZ", content)
        self.assertNotIn("SANTOS", content)

    def test_search_no_results(self):
        """Unmatched query returns empty table without crashing."""
        r = self._get("ZZZNOMATCH")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No Students Found")

    def test_search_empty_query_returns_all(self):
        """Blank q= returns all visible students."""
        r = self._get("")
        content = r.content.decode()
        self.assertIn("MARIA", content)
        self.assertIn("JUAN", content)
        self.assertIn("ANTONIO", content)

    def test_search_respects_scoping(self):
        """A student-role user searching only sees their own record."""
        student_user = User.objects.create_user(
            username="srch_student", password="p", role="student")
        self.s1.user = student_user
        self.s1.save()
        c = Client()
        c.login(username="srch_student", password="p")
        # Search for another student's last name
        r = c.get("/students/?q=REYES")
        self.assertEqual(r.status_code, 200)
        # The student table must show "No Students Found" —
        # REYES belongs to s3, which this student cannot see.
        # Note: "REYES" appears in the search input value, which is correct;
        # we assert the student DATA row is absent.
        self.assertContains(r, "No Students Found")
        self.assertNotIn("ANTONIO", r.content.decode())

    def test_search_form_in_page(self):
        """Search input element is present in the rendered HTML."""
        r = self._get()
        self.assertContains(r, 'name="q"')
        self.assertContains(r, 'Search</button>')

    def test_existing_list_unaffected(self):
        """/students/ with no query still returns all students (regression)."""
        r = self._get()
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        self.assertIn("MARIA", content)
        self.assertIn("JUAN", content)
        self.assertIn("ANTONIO", content)


# ---------------------------------------------------------------------------
# Medical Information tests — D[055]
# Approved decisions:
#   Q1-A: medical_condition, allergies, blood_type — all optional
#   Q2-A: not shown on list page
#   Q3-B: visible to staff only (enforced by existing @role_required on views)
# ---------------------------------------------------------------------------

import datetime as _dt


class StudentMedicalInfoTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(
            username="med_staff", password="p", role="adviser")
        self.student_user = User.objects.create_user(
            username="med_student_u", password="p", role="student")
        self.parent_user = User.objects.create_user(
            username="med_parent_u", password="p", role="parent")
        self.student = Student.objects.create(
            lrn="121708000099", first_name="HEALTH", last_name="TEST",
            gender="Male", birth_date=_dt.date(2007, 1, 1),
        )

    def test_medical_fields_blank_by_default(self):
        """New Student has all medical fields as empty string."""
        self.assertEqual(self.student.medical_condition, "")
        self.assertEqual(self.student.allergies, "")
        self.assertEqual(self.student.blood_type, "")

    def test_medical_fields_can_be_set(self):
        """Medical fields accept and persist values."""
        self.student.medical_condition = "Asthma"
        self.student.allergies = "Penicillin"
        self.student.blood_type = "O+"
        self.student.save()
        self.student.refresh_from_db()
        self.assertEqual(self.student.medical_condition, "Asthma")
        self.assertEqual(self.student.allergies, "Penicillin")
        self.assertEqual(self.student.blood_type, "O+")

    def test_blood_type_field_exists(self):
        """Student model has a blood_type CharField."""
        from django.db.models import CharField
        field = Student._meta.get_field("blood_type")
        self.assertIsInstance(field, CharField)
        self.assertEqual(field.max_length, 5)

    def test_medical_condition_field_exists(self):
        """Student model has a medical_condition CharField."""
        from django.db.models import CharField
        field = Student._meta.get_field("medical_condition")
        self.assertIsInstance(field, CharField)
        self.assertEqual(field.max_length, 200)

    def test_allergies_field_exists(self):
        """Student model has an allergies CharField."""
        from django.db.models import CharField
        field = Student._meta.get_field("allergies")
        self.assertIsInstance(field, CharField)
        self.assertEqual(field.max_length, 200)

    def test_edit_form_includes_medical_fields(self):
        """Staff can open student edit page which includes medical fields."""
        c = Client()
        c.login(username="med_staff", password="p")
        r = c.get(f"/students/edit/{self.student.pk}/")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        self.assertIn("medical_condition", content)
        self.assertIn("allergies", content)
        self.assertIn("blood_type", content)

    def test_student_and_parent_cannot_access_edit_form(self):
        """Student and parent roles cannot access the edit form (Q3-B, enforced by @role_required)."""
        for username in ("med_student_u", "med_parent_u"):
            c = Client()
            c.login(username=username, password="p")
            r = c.get(f"/students/edit/{self.student.pk}/")
            self.assertEqual(
                r.status_code, 403,
                f"User {username} must not access student edit form (Q3-B)",
            )

    def test_medical_info_not_on_student_list(self):
        """Medical fields do not appear as columns in the student list (Q2-A)."""
        self.student.medical_condition = "Asthma"
        self.student.blood_type = "O+"
        self.student.save()
        c = Client()
        c.login(username="med_staff", password="p")
        r = c.get("/students/")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        # The list page shows name/LRN/photo — not medical detail columns
        self.assertNotIn("<th>Medical", content)
        self.assertNotIn("<th>Blood", content)
        self.assertNotIn("<th>Allerg", content)
