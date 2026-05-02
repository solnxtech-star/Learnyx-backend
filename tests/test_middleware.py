from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.test import TestCase
from django.test import override_settings

from core.applications.users.models import School
from core.applications.users.models import User
from core.helper.tenants import get_current_db_alias
from core.helper.tenants import get_current_school
from core.middleware.tenant_middleware import CurrentSchoolMiddleware


@override_settings(ALLOWED_HOSTS=[
    "localhost",
    "greenfield.schoolapp.com",
    "brookside.schoolapp.com",
    "www.schoolapp.com",
    "api.schoolapp.com",
    "admin.schoolapp.com",
    "static.schoolapp.com",
    "portal.greenfield.edu.ng",
    "greenfield.otherdomain.com",
])
class MiddlewareTests(TestCase):

    def setUp(self):
        """
        Set up two schools and a user for testing.
        """
        self.factory      = RequestFactory()
        self.get_response = lambda req: None

        self.school_a = School.objects.create(
            name="GreenField Academy",
            slug="greenfield",
        )
        self.school_b = School.objects.create(
            name="Brookside High",
            slug="brookside",
        )
        self.user_a = User.objects.create_user(
            email="a@greenfield.com",
            password="pass",
            school=self.school_a,
        )
        self.middleware = CurrentSchoolMiddleware(self.get_response)

    # ------------------------------------------------------------------
    # Resolution strategy 1 — subdomain
    # ------------------------------------------------------------------

    def test_resolves_school_from_subdomain(self):
        """
        Request with subdomain should resolve to the correct school.
        'greenfield.schoolapp.com' → school_a
        """
        request = self.factory.get("/", HTTP_HOST="greenfield.schoolapp.com")
        request.user = AnonymousUser()
        self.middleware(request)

        self.assertEqual(request.current_school, self.school_a)
        self.assertEqual(request.current_db_alias, "default")

    def test_subdomain_inactive_school_not_resolved(self):
        """
        If a school is inactive, it should not resolve even if subdomain matches.
        'greenfield.schoolapp.com' → None (because school_a is inactive)
        """
        self.school_a.is_active = False
        self.school_a.save()

        request = self.factory.get("/", HTTP_HOST="greenfield.schoolapp.com")
        request.user = AnonymousUser()
        self.middleware(request)

        self.assertIsNone(request.current_school)

    def test_reserved_subdomain_not_resolved(self):
        """
        Reserved subdomains should never resolve to a school.
        'www.schoolapp.com'    → None
        'api.schoolapp.com'    → None
        'admin.schoolapp.com'  → None
        'static.schoolapp.com' → None
        """
        for subdomain in ["www", "api", "admin", "static"]:
            request = self.factory.get(
                "/", HTTP_HOST=f"{subdomain}.schoolapp.com"
            )
            request.user = AnonymousUser()
            self.middleware(request)
            self.assertIsNone(
                request.current_school,
                msg=f"'{subdomain}' should not resolve to a school",
            )

    def test_localhost_not_resolved_via_subdomain(self):
        """
        localhost has only one part — no subdomain.
        Falls through to user resolver.
        Anonymous user + no subdomain → None.
        """
        request = self.factory.get("/", HTTP_HOST="localhost:8000")
        request.user = AnonymousUser()
        self.middleware(request)

        self.assertIsNone(request.current_school)

    # ------------------------------------------------------------------
    # Resolution strategy 2 — custom domain
    # ------------------------------------------------------------------

    def test_resolves_school_from_custom_domain(self):
        """
        Full host matches school's registered custom_domain field.
        'portal.greenfield.edu.ng' → school_a
        """
        self.school_a.custom_domain = "portal.greenfield.edu.ng"
        self.school_a.save()

        request = self.factory.get("/", HTTP_HOST="portal.greenfield.edu.ng")
        request.user = AnonymousUser()
        self.middleware(request)

        self.assertEqual(request.current_school, self.school_a)

    # ------------------------------------------------------------------
    # Resolution strategy 3 — authenticated user
    # ------------------------------------------------------------------

    def test_resolves_school_from_user(self):
        """
        No subdomain or custom domain — falls back to user.school.
        'localhost:8000' + authenticated user_a → school_a
        """
        request = self.factory.get("/", HTTP_HOST="localhost:8000")
        request.user = self.user_a
        self.middleware(request)

        self.assertEqual(request.current_school, self.school_a)

    def test_anonymous_user_no_school(self):
        """
        No subdomain, no custom domain, anonymous user → None.
        """
        request = self.factory.get("/", HTTP_HOST="localhost:8000")
        request.user = AnonymousUser()
        self.middleware(request)

        self.assertIsNone(request.current_school)

    # ------------------------------------------------------------------
    # Thread-local cleanup
    # ------------------------------------------------------------------

    def test_thread_local_cleared_after_request(self):
        """
        After request completes normally, thread-local must be None.
        Prevents school context leaking into the next request
        that reuses this thread.
        """
        request = self.factory.get("/", HTTP_HOST="greenfield.schoolapp.com")
        request.user = AnonymousUser()
        self.middleware(request)

        self.assertIsNone(get_current_school())
        self.assertEqual(get_current_db_alias(), "default")

    def test_thread_local_cleared_even_on_exception(self):
        """
        Even if the view crashes, thread-local must still be cleared.
        The finally block in middleware.__call__ guarantees this.
        """
        def bad_response(req):
            raise RuntimeError("Something broke in the view")

        middleware = CurrentSchoolMiddleware(bad_response)
        request    = self.factory.get("/", HTTP_HOST="greenfield.schoolapp.com")
        request.user = AnonymousUser()

        with self.assertRaises(RuntimeError):
            middleware(request)

        # finally block must have fired despite the exception
        self.assertIsNone(get_current_school())
        self.assertEqual(get_current_db_alias(), "default")

    # ------------------------------------------------------------------
    # Priority — custom domain wins over subdomain
    # ------------------------------------------------------------------

    def test_custom_domain_takes_priority_over_subdomain(self):
        """
        school_b registers 'greenfield.otherdomain.com' as its custom domain.
        Even though 'greenfield' looks like school_a's subdomain,
        custom domain resolution runs first and returns school_b.
        """
        self.school_b.custom_domain = "greenfield.otherdomain.com"
        self.school_b.save()

        request = self.factory.get("/", HTTP_HOST="greenfield.otherdomain.com")
        request.user = AnonymousUser()
        self.middleware(request)

        self.assertEqual(request.current_school, self.school_b)
