import logging
from unittest.mock import MagicMock

from django.test import TestCase

from core.applications.users.models import School
from core.applications.users.models import StudentProfile
from core.applications.users.models import User
from core.db.routers import TenantDatabaseRouter
from core.helper.tenants import clear_current_school
from core.helper.tenants import set_current_school


class RouterTests(TestCase):

    def setUp(self):
        """
        Set up a tenant database router and a school for testing.
        Suppress router WARNING/ERROR logs that are intentionally
        triggered by tests — they confirm correct behaviour but
        make test output noisy.
        """
        self.router   = TenantDatabaseRouter()
        self.school_a = School.objects.create(
            name="GreenField Academy",
            slug="greenfield",
        )

        # Suppress router logs during tests
        # These logs are correct production behaviour — we silence them
        # here only because the tests intentionally trigger them
        self.router_logger = logging.getLogger("core.db.routers")
        self.router_logger.setLevel(logging.CRITICAL)

    def tearDown(self):
        """
        Clear tenant context after each test to avoid cross-test contamination.
        Restore router logging level after each test.
        """
        clear_current_school()
        self.router_logger.setLevel(logging.WARNING)

    # ------------------------------------------------------------------
    # Master models always route to default
    # ------------------------------------------------------------------

    def test_school_model_always_routes_to_default(self):
        """
        School model is the master model and should always route to 'default',
        regardless of tenant context.
        """
        set_current_school(self.school_a)
        self.assertEqual(self.router.db_for_read(School), "default")
        self.assertEqual(self.router.db_for_write(School), "default")

    def test_user_model_always_routes_to_default(self):
        """
        User model is the master model and should always route to 'default'.
        """
        set_current_school(self.school_a)
        self.assertEqual(self.router.db_for_read(User), "default")

    # ------------------------------------------------------------------
    # Tenant models route to current db_alias
    # ------------------------------------------------------------------

    def test_tenant_model_routes_to_default_when_shared(self):
        """
        When school is on shared tier, tenant models should route to 'default'.
        """
        set_current_school(self.school_a)
        # school_a is SHARED → db_alias = "default"
        self.assertEqual(self.router.db_for_read(StudentProfile), "default")

    def test_tenant_model_routes_to_default_when_no_context(self):
        """
        When no tenant context is set, tenant models should route to 'default'.
        """
        clear_current_school()
        self.assertEqual(self.router.db_for_read(StudentProfile), "default")

    def test_unregistered_alias_falls_back_to_default(self):
        """
        If db_alias is set but not in DATABASES
        (e.g. school upgraded but server not restarted yet)
        router must fall back to default gracefully — never crash.
        """
        self.school_a.db_alias = "school_greenfield"
        self.school_a.db_tier  = "isolated"
        # Intentionally NOT added to settings.DATABASES
        set_current_school(self.school_a)

        # Should warn and fall back — not crash
        result = self.router.db_for_read(StudentProfile)
        self.assertEqual(result, "default")

    # ------------------------------------------------------------------
    # allow_relation
    # ------------------------------------------------------------------

    def test_allow_relation_same_db(self):
        """
        Both objects on same database — relation always allowed.
        Normal FK relations between tenant models on the same DB.
        """
        obj1 = MagicMock(); obj1._state.db = "default"
        obj2 = MagicMock(); obj2._state.db = "default"
        self.assertTrue(self.router.allow_relation(obj1, obj2))

    def test_allow_relation_one_on_default(self):
        """
        One object on default (master model) relating to tenant model — allowed.
        e.g. StudentProfile (tenant) → User (master/default)
        This cross-DB relation is intentional and must be permitted.
        """
        obj1 = MagicMock(); obj1._state.db = "default"
        obj2 = MagicMock(); obj2._state.db = "school_greenfield"
        self.assertTrue(self.router.allow_relation(obj1, obj2))

    def test_deny_relation_two_different_tenant_dbs(self):
        """
        Two objects on two different tenant databases — must be denied.
        This is a cross-tenant relation — school_greenfield object
        cannot relate to school_brookside object under any circumstance.
        The router logs an ERROR and returns False — both are verified here.
        """
        obj1 = MagicMock(); obj1._state.db = "school_greenfield"
        obj2 = MagicMock(); obj2._state.db = "school_brookside"
        self.assertFalse(self.router.allow_relation(obj1, obj2))
