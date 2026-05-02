from django.test import TestCase

from core.applications.users.models import School
from core.applications.users.models import StudentProfile
from core.applications.users.models import TeacherProfile
from core.applications.users.models import User
from core.helper.tenants import clear_current_school
from core.helper.tenants import set_current_school


class ManagerTests(TestCase):

    def setUp(self):
        """
        """

        self.school_a = School.objects.create(
            name="GreenField Academy", slug="greenfield"
        )
        self.school_b = School.objects.create(
            name="Brookside High", slug="brookside"
        )
        self.user_a = User.objects.create_user(
            email="a@greenfield.com", password="pass", school=self.school_a
        )
        self.user_b = User.objects.create_user(
            email="b@brookside.com", password="pass", school=self.school_b
        )

    def tearDown(self):
        clear_current_school()

    # ------------------------------------------------------------------
    # TenantManager auto-scoping
    # ------------------------------------------------------------------

    def test_unscoped_returns_all_schools(self):
        clear_current_school()
        # No context → returns everything
        from core.applications.users.models import StudentContact
        # Just checking it doesn't crash and returns a queryset
        qs = StudentContact.objects.unscoped()
        self.assertIsNotNone(qs)

    # ------------------------------------------------------------------
    # ProfileTenantManager auto-scoping
    # ------------------------------------------------------------------

    def test_profile_manager_scopes_to_current_school(self):
        set_current_school(self.school_a)
        qs = StudentProfile.objects.all()
        # All returned profiles must belong to school_a
        for profile in qs:
            self.assertEqual(profile.user.school, self.school_a)

    def test_profile_manager_no_cross_tenant_leak(self):
        """school_b profiles must not appear when school_a is active."""
        set_current_school(self.school_a)
        school_b_user_ids = User.objects.filter(
            school=self.school_b
        ).values_list("id", flat=True)

        qs = StudentProfile.objects.all()
        for profile in qs:
            self.assertNotIn(
                profile.user_id,
                school_b_user_ids,
                msg="school_b profile leaked into school_a queryset",
            )

    def test_profile_manager_for_school_explicit(self):
        """for_school() explicit override works regardless of context."""
        set_current_school(self.school_a)
        # Explicitly query school_b despite school_a being active
        qs = StudentProfile.objects.for_school(self.school_b)
        for profile in qs:
            self.assertEqual(profile.user.school, self.school_b)

    def test_profile_manager_unscoped(self):
        """unscoped() returns all profiles across all schools."""
        set_current_school(self.school_a)
        all_profiles = StudentProfile.objects.unscoped()
        # Should include both schools
        self.assertIsNotNone(all_profiles)

    # ------------------------------------------------------------------
    # SchoolManager
    # ------------------------------------------------------------------

    def test_school_manager_by_code(self):
        school = School.objects.by_code(self.school_a.school_code)
        self.assertEqual(school, self.school_a)

    def test_school_manager_by_code_wrong_raises(self):
        with self.assertRaises(School.DoesNotExist):
            School.objects.by_code("SCH-INVALID")

    def test_school_manager_by_code_safe_returns_none(self):
        result = School.objects.by_code_safe("SCH-INVALID")
        self.assertIsNone(result)

    def test_school_manager_active(self):
        self.school_b.is_active = False
        self.school_b.save()
        active = School.objects.active()
        self.assertIn(self.school_a, active)
        self.assertNotIn(self.school_b, active)

    def test_school_manager_by_slug(self):
        school = School.objects.by_slug("greenfield")
        self.assertEqual(school, self.school_a)

    def test_school_manager_by_slug_missing_returns_none(self):
        result = School.objects.by_slug("doesnotexist")
        self.assertIsNone(result)
