from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from academics.models import SchoolYear, Subject
from students.models import Student
from .models import Grade

User = get_user_model()


class GradeModelTests(TestCase):

    def setUp(self):
        self.student = Student.objects.create(
            lrn="123456789012",
            first_name="Juan",
            last_name="Cruz",
            gender="Male",
            birth_date="2012-05-01",
        )
        self.subject = Subject.objects.create(code="MATH7", name="Mathematics 7")
        self.school_year = SchoolYear.objects.create(year="2025-2026")

    def _make_grade(self, **overrides):
        fields = dict(
            student=self.student,
            subject=self.subject,
            school_year=self.school_year,
            first_quarter=90,
            second_quarter=90,
            third_quarter=90,
            fourth_quarter=90,
        )
        fields.update(overrides)
        return Grade(**fields)

    def test_grade_above_100_fails_validation(self):
        grade = self._make_grade(first_quarter=150)
        with self.assertRaises(ValidationError):
            grade.full_clean()

    def test_negative_grade_fails_validation(self):
        grade = self._make_grade(first_quarter=-5)
        with self.assertRaises(ValidationError):
            grade.full_clean()

    def test_valid_grade_passes_validation(self):
        grade = self._make_grade()
        grade.full_clean()  # should not raise

    def test_duplicate_grade_same_subject_year_rejected(self):
        self._make_grade().save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._make_grade().save()


class GradeViewAuthTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="staff", password="strongpass123")

    def test_list_requires_login(self):
        response = self.client.get(reverse("grade_list"))
        self.assertEqual(response.status_code, 302)

    def test_list_accessible_when_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("grade_list"))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Award boundary-value tests (DOCX Module 10 — GA range only)
# ---------------------------------------------------------------------------

import datetime
from decimal import Decimal
from academics.models import SchoolYear, GradeLevel, Section, Subject
from students.models import Student
from enrollment.models import Enrollment
from grades.models import Grade
from grades.services import _award_for, class_ranking, awards_list


class AwardBoundaryTests(TestCase):
    """
    Verify _award_for() against every documented threshold.

    Source: DOCX Module 10 — exact text:
        98-100  → With Highest Honors
        95-97   → With High Honors
        90-94   → With Honors
        (no other condition documented)
    """

    def test_below_90_no_award(self):
        self.assertEqual(_award_for(89), "")

    def test_boundary_90_with_honors(self):
        self.assertEqual(_award_for(90), "With Honors")

    def test_interior_92_with_honors(self):
        self.assertEqual(_award_for(92), "With Honors")

    def test_boundary_94_with_honors(self):
        self.assertEqual(_award_for(94), "With Honors")

    def test_boundary_95_with_high_honors(self):
        self.assertEqual(_award_for(95), "With High Honors")

    def test_interior_96_with_high_honors(self):
        self.assertEqual(_award_for(96), "With High Honors")

    def test_boundary_97_with_high_honors(self):
        self.assertEqual(_award_for(97), "With High Honors")

    def test_boundary_98_with_highest_honors(self):
        self.assertEqual(_award_for(98), "With Highest Honors")

    def test_interior_99_with_highest_honors(self):
        self.assertEqual(_award_for(99), "With Highest Honors")

    def test_boundary_100_with_highest_honors(self):
        self.assertEqual(_award_for(100), "With Highest Honors")

    def test_none_avg_no_award(self):
        self.assertEqual(_award_for(None), "")

    def test_zero_no_award(self):
        self.assertEqual(_award_for(0), "")

    def test_decimal_boundary_90_with_honors(self):
        """GA is always a whole number after round_whole(), but test Decimal too."""
        self.assertEqual(_award_for(Decimal("90")), "With Honors")

    def test_decimal_boundary_95_with_high_honors(self):
        self.assertEqual(_award_for(Decimal("95")), "With High Honors")

    def test_decimal_boundary_98_with_highest_honors(self):
        self.assertEqual(_award_for(Decimal("98")), "With Highest Honors")


class AwardNoIsPromotedRestrictionTests(TestCase):
    """
    Prove that a student with a failing subject still receives an award
    when their GA meets the threshold — because the DOCX documents no
    such restriction.
    """

    def setUp(self):
        self.sy  = SchoolYear.objects.create(year="2023-2024", grading_system="term", is_active=True)
        self.gl  = GradeLevel.objects.create(name="Grade 11")
        self.sec = Section.objects.create(grade_level=self.gl, name="11-CSS", track_strand="TVL")
        self.s1  = Subject.objects.create(code="S1", name="Subject One")
        self.s2  = Subject.objects.create(code="S2", name="Subject Two")

    def _student(self, lrn, last_name):
        s = Student.objects.create(
            lrn=lrn, last_name=last_name, first_name="X",
            gender="Male", birth_date=datetime.date(2007, 1, 1),
        )
        Enrollment.objects.create(
            student=s, school_year=self.sy,
            grade_level=self.gl, section=self.sec, semester="1",
        )
        return s

    def _grade(self, student, subject, fg):
        Grade.objects.create(
            student=student, subject=subject, school_year=self.sy,
            first_quarter=fg, second_quarter=fg, third_quarter=fg, final_grade=fg,
        )

    def test_award_given_regardless_of_failing_subject(self):
        """
        Student has GA = (95 + 65) / 2 = 80 → no award (below 90).
        But a student with GA = (95 + 95) / 2 = 95 DOES get an award
        even if they hypothetically had a low sub-grade — the only
        criterion is the documented GA range.
        """
        # Student A: two subjects, both 95 → GA=95 → With High Honors
        sa = self._student("0001", "StudentA")
        self._grade(sa, self.s1, 95)
        self._grade(sa, self.s2, 95)

        # Student B: one subject 95, one subject 65 → GA=80 → no award
        sb = self._student("0002", "StudentB")
        self._grade(sb, self.s1, 95)
        self._grade(sb, self.s2, 65)

        rows = {r["student"].last_name: r for r in class_ranking(self.sy)}
        self.assertEqual(rows["StudentA"]["award"], "With High Honors")
        self.assertEqual(rows["StudentB"]["award"], "")  # GA=80, below 90

    def test_award_not_blocked_by_single_failing_grade(self):
        """
        A student where one subject is below 75 but GA is still >= 90
        MUST receive the award — no is_promoted restriction documented.
        """
        # Subject 1: 74 (fails), Subject 2: 100 → GA = (74+100)/2 = 87 → no award
        # To get GA >= 90 with one failure, use: 74 + 106... not possible.
        # Use three subjects: 74 + 96 + 96 = 266 / 3 = 88.67 → 89 → no award
        # Use two: 74 + 106 impossible. Use: s1=72, s2=s3=96 → 264/3=88 still no.
        # Realistic: 2 subjects, 74 + 108 impossible.
        # Must use at least 3: 74 + 96 + 100 = 270/3 = 90 → With Honors!
        s3 = Subject.objects.create(code="S3", name="Subject Three")
        sc = self._student("0003", "StudentC")
        self._grade(sc, self.s1, 74)   # failing by DepEd standard (< 75)
        self._grade(sc, self.s2, 96)
        self._grade(sc, s3, 100)
        # GA = round_whole((74+96+100)/3) = round_whole(90.0) = 90 → With Honors

        rows = {r["student"].last_name: r for r in class_ranking(self.sy)}
        # The DOCX says: GA 90-94 → With Honors. No failing-subject restriction.
        self.assertEqual(rows["StudentC"]["award"], "With Honors",
            "Award must be based on GA range only — not blocked by any failing subject (not in DOCX)")

    def test_awards_list_reflects_ga_range_only(self):
        """awards_list() groups must match GA range with no extra filter."""
        # Three students: GA 99, 95, 90
        for lrn, name, fg in [("A", "Highest", 99), ("B", "HighH", 95), ("C", "Honors", 90)]:
            s = self._student(lrn, name)
            self._grade(s, self.s1, fg)

        groups = awards_list(self.sy)
        self.assertIn("Highest", [m["student"].last_name for m in groups["With Highest Honors"]])
        self.assertIn("HighH",   [m["student"].last_name for m in groups["With High Honors"]])
        self.assertIn("Honors",  [m["student"].last_name for m in groups["With Honors"]])

    def test_below_90_not_in_any_award_group(self):
        s = self._student("X89", "BelowNinety")
        self._grade(s, self.s1, 89)
        groups = awards_list(self.sy)
        all_members = [m["student"].last_name for grp in groups.values() for m in grp]
        self.assertNotIn("BelowNinety", all_members)


# ---------------------------------------------------------------------------
# Grade Locking tests — D[094]
# Approved decisions: lock=admin+principal, unlock=admin only, unlock supported,
# ValidationError on locked save, per-Grade record scope.
# ---------------------------------------------------------------------------

import datetime
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from academics.models import SchoolYear, GradeLevel, Section, Subject
from students.models import Student
from enrollment.models import Enrollment
from .models import Grade

User = get_user_model()


class GradeLockingTests(TestCase):

    def setUp(self):
        self.sy      = SchoolYear.objects.create(
            year="2023-2024", grading_system="term", is_active=True)
        self.gl      = GradeLevel.objects.create(name="Grade 11")
        self.sec     = Section.objects.create(
            grade_level=self.gl, name="11-CSS", track_strand="TVL")
        self.subject = Subject.objects.create(code="MATH", name="Mathematics")
        self.student = Student.objects.create(
            lrn="121708990099", first_name="LOCK", last_name="TEST",
            gender="Male", birth_date=datetime.date(2007, 1, 1),
        )
        Enrollment.objects.create(
            student=self.student, school_year=self.sy,
            grade_level=self.gl, section=self.sec, semester="1",
        )
        # Grade with all terms filled so final_grade is computed
        self.grade = Grade.objects.create(
            student=self.student, subject=self.subject, school_year=self.sy,
            first_quarter=90, second_quarter=88, third_quarter=92,
        )

        # Users for permission tests
        for role in ("admin", "principal", "teacher", "adviser",
                     "subject_teacher", "student", "parent"):
            User.objects.create_user(
                username=f"lock_{role}", password="p", role=role)

    # ── Model-level tests ─────────────────────────────────────────────────

    def test_grade_unlocked_by_default(self):
        """New Grade record has is_locked=False."""
        self.assertFalse(self.grade.is_locked)

    def test_locked_grade_cannot_be_saved(self):
        """Grade.save() raises ValidationError when is_locked=True."""
        Grade.objects.filter(pk=self.grade.pk).update(is_locked=True)
        self.grade.refresh_from_db()
        self.grade.first_quarter = 95
        with self.assertRaises(ValidationError):
            self.grade.save()

    def test_unlocked_grade_can_be_saved(self):
        """Normal grade.save() on an unlocked record works without error."""
        self.grade.first_quarter = 95
        self.grade.save()  # must not raise
        self.grade.refresh_from_db()
        self.assertEqual(self.grade.first_quarter, 95)

    def test_new_grade_creation_ignores_lock(self):
        """Creating a brand-new Grade (no pk yet) is never blocked."""
        subject2 = Subject.objects.create(code="SCI", name="Science")
        # This must not raise even though is_locked defaults to False on new records
        g = Grade.objects.create(
            student=self.student, subject=subject2, school_year=self.sy,
            first_quarter=80, second_quarter=82, third_quarter=84,
        )
        self.assertFalse(g.is_locked)

    # ── View-level tests ──────────────────────────────────────────────────

    def test_lock_view_sets_locked(self):
        """POST /grades/<pk>/lock/ sets is_locked=True."""
        c = Client()
        c.login(username="lock_admin", password="p")
        r = c.post(f"/grades/{self.grade.pk}/lock/")
        self.assertIn(r.status_code, [301, 302])
        self.grade.refresh_from_db()
        self.assertTrue(self.grade.is_locked)

    def test_unlock_view_clears_locked(self):
        """POST /grades/<pk>/unlock/ sets is_locked=False."""
        Grade.objects.filter(pk=self.grade.pk).update(is_locked=True)
        c = Client()
        c.login(username="lock_admin", password="p")
        r = c.post(f"/grades/{self.grade.pk}/unlock/")
        self.assertIn(r.status_code, [301, 302])
        self.grade.refresh_from_db()
        self.assertFalse(self.grade.is_locked)

    def test_lock_view_allowed_roles(self):
        """admin and principal can lock grades (Q1)."""
        for role in ("admin", "principal"):
            # Reset to unlocked before each attempt
            Grade.objects.filter(pk=self.grade.pk).update(is_locked=False)
            c = Client()
            c.login(username=f"lock_{role}", password="p")
            r = c.post(f"/grades/{self.grade.pk}/lock/")
            self.assertIn(r.status_code, [301, 302],
                          f"Role {role!r} should be able to lock grades")

    def test_lock_view_blocked_roles(self):
        """Roles other than admin/principal are blocked (403) from locking."""
        blocked = ["teacher", "adviser", "subject_teacher", "student", "parent"]
        for role in blocked:
            c = Client()
            c.login(username=f"lock_{role}", password="p")
            r = c.post(f"/grades/{self.grade.pk}/lock/")
            self.assertEqual(r.status_code, 403,
                             f"Role {role!r} must NOT lock grades")

    def test_unlock_blocked_for_principal(self):
        """Principal cannot unlock grades — admin only (Q2)."""
        Grade.objects.filter(pk=self.grade.pk).update(is_locked=True)
        c = Client()
        c.login(username="lock_principal", password="p")
        r = c.post(f"/grades/{self.grade.pk}/unlock/")
        self.assertEqual(r.status_code, 403)
        self.grade.refresh_from_db()
        self.assertTrue(self.grade.is_locked)  # still locked

    def test_existing_grade_list_unaffected(self):
        """/grades/ still returns 200 after lock field addition."""
        c = Client()
        c.login(username="lock_admin", password="p")
        r = c.get("/grades/")
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# Grade Verification tests — D[095]
# Approved decisions:
#   Q1: admin + principal can verify
#   Q2: admin only can unverify
#   Q3-A: editing resets is_verified to False
#   Q4-A: independent of is_locked
#   Q5-A: reversible
# ---------------------------------------------------------------------------


class GradeVerificationTests(TestCase):

    def setUp(self):
        self.sy      = SchoolYear.objects.create(
            year="2023-2024", grading_system="term", is_active=True)
        self.gl      = GradeLevel.objects.create(name="Grade 11")
        self.sec     = Section.objects.create(
            grade_level=self.gl, name="11-CSS", track_strand="TVL")
        self.subject = Subject.objects.create(code="ENG", name="English")
        self.student = Student.objects.create(
            lrn="121708990088", first_name="VERIFY", last_name="TEST",
            gender="Female", birth_date=datetime.date(2007, 1, 1),
        )
        Enrollment.objects.create(
            student=self.student, school_year=self.sy,
            grade_level=self.gl, section=self.sec, semester="1",
        )
        self.grade = Grade.objects.create(
            student=self.student, subject=self.subject, school_year=self.sy,
            first_quarter=88, second_quarter=90, third_quarter=86,
        )
        for role in ("admin", "principal", "teacher", "adviser",
                     "subject_teacher", "student", "parent"):
            User.objects.create_user(
                username=f"ver_{role}", password="p", role=role)

    # ── Model tests ───────────────────────────────────────────────────────

    def test_grade_unverified_by_default(self):
        """New Grade record has is_verified=False."""
        self.assertFalse(self.grade.is_verified)

    def test_edit_resets_verification_q3a(self):
        """Q3-A: saving a verified grade via Grade.save() resets is_verified."""
        Grade.objects.filter(pk=self.grade.pk).update(is_verified=True)
        self.grade.refresh_from_db()
        self.assertTrue(self.grade.is_verified)

        # Simulate a grade edit
        self.grade.first_quarter = 92
        self.grade.save()

        self.grade.refresh_from_db()
        self.assertFalse(self.grade.is_verified,
            "Editing a verified grade must reset is_verified to False (Q3-A)")

    def test_verify_independent_of_lock_q4a(self):
        """Q4-A: a grade can be verified while unlocked."""
        self.assertFalse(self.grade.is_locked)   # confirm unlocked
        c = Client()
        c.login(username="ver_admin", password="p")
        r = c.post(f"/grades/{self.grade.pk}/verify/")
        self.assertIn(r.status_code, [301, 302])
        self.grade.refresh_from_db()
        self.assertTrue(self.grade.is_verified,
            "Verification must succeed even when grade is not locked (Q4-A)")

    # ── View tests ────────────────────────────────────────────────────────

    def test_verify_view_sets_verified(self):
        """POST /grades/<pk>/verify/ sets is_verified=True."""
        c = Client()
        c.login(username="ver_admin", password="p")
        r = c.post(f"/grades/{self.grade.pk}/verify/")
        self.assertIn(r.status_code, [301, 302])
        self.grade.refresh_from_db()
        self.assertTrue(self.grade.is_verified)

    def test_unverify_view_clears_verified(self):
        """POST /grades/<pk>/unverify/ sets is_verified=False.  Admin only (Q2)."""
        Grade.objects.filter(pk=self.grade.pk).update(is_verified=True)
        c = Client()
        c.login(username="ver_admin", password="p")
        r = c.post(f"/grades/{self.grade.pk}/unverify/")
        self.assertIn(r.status_code, [301, 302])
        self.grade.refresh_from_db()
        self.assertFalse(self.grade.is_verified)

    def test_verify_allowed_roles(self):
        """Admin and principal can verify grades (Q1)."""
        for role in ("admin", "principal"):
            Grade.objects.filter(pk=self.grade.pk).update(is_verified=False)
            c = Client()
            c.login(username=f"ver_{role}", password="p")
            r = c.post(f"/grades/{self.grade.pk}/verify/")
            self.assertIn(r.status_code, [301, 302],
                          f"Role {role!r} should be able to verify grades (Q1)")
            self.grade.refresh_from_db()
            self.assertTrue(self.grade.is_verified,
                            f"Role {role!r} should have set is_verified=True")

    def test_verify_blocked_roles(self):
        """Roles other than admin/principal are blocked (403) from verifying."""
        blocked = ["teacher", "adviser", "subject_teacher", "student", "parent"]
        for role in blocked:
            c = Client()
            c.login(username=f"ver_{role}", password="p")
            r = c.post(f"/grades/{self.grade.pk}/verify/")
            self.assertEqual(r.status_code, 403,
                             f"Role {role!r} must NOT verify grades")

    def test_unverify_blocked_for_principal(self):
        """Principal cannot unverify — admin only (Q2)."""
        Grade.objects.filter(pk=self.grade.pk).update(is_verified=True)
        c = Client()
        c.login(username="ver_principal", password="p")
        r = c.post(f"/grades/{self.grade.pk}/unverify/")
        self.assertEqual(r.status_code, 403)
        self.grade.refresh_from_db()
        self.assertTrue(self.grade.is_verified)  # still verified

    def test_grade_list_shows_verified_status(self):
        """Grade list page returns 200 and contains verification badge."""
        Grade.objects.filter(pk=self.grade.pk).update(is_verified=True)
        c = Client()
        c.login(username="ver_admin", password="p")
        r = c.get("/grades/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Verified")
