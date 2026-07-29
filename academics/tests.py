import datetime
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from .models import Event

User = get_user_model()

EVENT_URL      = "/events/"
CREATE_URL     = "/events/create/"
DASHBOARD_URL  = "/dashboard/"


class EventModelTests(TestCase):

    def test_event_str(self):
        e = Event(title="Brigada Eskwela", event_date=datetime.date.today())
        self.assertEqual(str(e), "Brigada Eskwela")

    def test_event_ordering(self):
        """Events ordered by event_date ascending."""
        Event.objects.create(title="Later",   event_date=datetime.date(2025, 6, 15))
        Event.objects.create(title="Earlier", event_date=datetime.date(2025, 6, 1))
        titles = list(Event.objects.values_list("title", flat=True))
        self.assertEqual(titles, ["Earlier", "Later"])


class EventViewPermissionTests(TestCase):

    def setUp(self):
        self.roles = [
            "admin", "principal", "ict_coordinator",
            "teacher", "adviser", "subject_teacher",
            "student", "parent",
        ]
        for role in self.roles:
            User.objects.create_user(username=f"u_{role}", password="p", role=role)

    def _client(self, role):
        c = Client()
        c.login(username=f"u_{role}", password="p")
        return c

    def test_event_list_all_roles(self):
        for role in self.roles:
            r = self._client(role).get(EVENT_URL)
            self.assertEqual(r.status_code, 200,
                             f"Role {role!r} should access /events/ (R3)")

    def test_event_list_unauthenticated(self):
        r = Client().get(EVENT_URL)
        self.assertIn(r.status_code, [301, 302])

    def test_event_create_get_admin(self):
        self.assertEqual(self._client("admin").get(CREATE_URL).status_code, 200)

    def test_event_create_get_principal(self):
        self.assertEqual(self._client("principal").get(CREATE_URL).status_code, 200)

    def test_event_create_get_ict(self):
        self.assertEqual(self._client("ict_coordinator").get(CREATE_URL).status_code, 200)

    def test_event_create_post_creates_record(self):
        before = Event.objects.count()
        self._client("admin").post(CREATE_URL, {
            "title":      "Faculty Meeting",
            "event_date": "2025-09-01",
            "description": "Monthly faculty meeting",
        })
        self.assertEqual(Event.objects.count(), before + 1)
        self.assertEqual(Event.objects.latest("created_at").title, "Faculty Meeting")

    def test_event_create_blocked_student(self):
        self.assertEqual(self._client("student").get(CREATE_URL).status_code, 403)

    def test_event_create_blocked_parent(self):
        self.assertEqual(self._client("parent").get(CREATE_URL).status_code, 403)

    def test_event_create_blocked_adviser(self):
        self.assertEqual(self._client("adviser").get(CREATE_URL).status_code, 403)

    def test_event_create_blocked_subject_teacher(self):
        self.assertEqual(self._client("subject_teacher").get(CREATE_URL).status_code, 403)


class EventDashboardTests(TestCase):

    def setUp(self):
        for role in ("admin", "student", "parent"):
            User.objects.create_user(username=f"u_{role}", password="p", role=role)
        Event.objects.create(
            title="UNIQUE_FUTURE_EVENT",
            event_date=datetime.date.today() + datetime.timedelta(days=3),
        )
        Event.objects.create(
            title="UNIQUE_PAST_EVENT",
            event_date=datetime.date.today() - datetime.timedelta(days=3),
        )

    def _client(self, role):
        c = Client()
        c.login(username=f"u_{role}", password="p")
        return c

    def test_upcoming_on_admin_dashboard(self):
        self.assertContains(self._client("admin").get(DASHBOARD_URL),
                            "UNIQUE_FUTURE_EVENT")

    def test_upcoming_on_student_dashboard(self):
        self.assertContains(self._client("student").get(DASHBOARD_URL),
                            "UNIQUE_FUTURE_EVENT")

    def test_upcoming_on_parent_dashboard(self):
        self.assertContains(self._client("parent").get(DASHBOARD_URL),
                            "UNIQUE_FUTURE_EVENT")

    def test_past_event_not_in_dashboard_upcoming(self):
        """Past event is excluded from the upcoming query (event_date__gte=today)."""
        r = self._client("admin").get(DASHBOARD_URL)
        upcoming = r.context.get("upcoming_events", [])
        titles = [e.title for e in upcoming]
        self.assertNotIn("UNIQUE_PAST_EVENT", titles)
        self.assertIn("UNIQUE_FUTURE_EVENT", titles)


class EventNavbarBadgeTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="u_badge", password="p", role="admin")

    def test_navbar_badge_shows_count(self):
        Event.objects.create(
            title="This Week Event",
            event_date=datetime.date.today() + datetime.timedelta(days=2),
        )
        c = Client()
        c.login(username="u_badge", password="p")
        r = c.get(DASHBOARD_URL)
        self.assertEqual(r.context.get("events_this_week"), 1)

    def test_navbar_no_badge_when_no_events(self):
        c = Client()
        c.login(username="u_badge", password="p")
        r = c.get(DASHBOARD_URL)
        self.assertEqual(r.context.get("events_this_week"), 0)


class EventRegressionTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="u_reg", password="p", role="admin")

    def _get(self, url):
        c = Client()
        c.login(username="u_reg", password="p")
        return c.get(url)

    def test_sf9_unaffected(self):
        self.assertEqual(self._get("/reports/sf9/").status_code, 200)

    def test_sf10_unaffected(self):
        self.assertEqual(self._get("/reports/sf10/export/").status_code, 200)

    def test_sf1_import_unaffected(self):
        self.assertEqual(self._get("/reports/sf1/import/").status_code, 200)

    def test_id_maker_unaffected(self):
        self.assertEqual(self._get("/reports/id/student/").status_code, 200)

    def test_certificates_unaffected(self):
        self.assertEqual(self._get("/reports/certificates/").status_code, 200)

    def test_class_ranking_unaffected(self):
        self.assertEqual(self._get("/grades/ranking/class/").status_code, 200)

    def test_qr_session_create_unaffected(self):
        self.assertEqual(self._get("/attendance/qr/create/").status_code, 200)
