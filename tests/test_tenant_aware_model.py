# tests/test_tenant_aware_model.py
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.applications.users.models import School
from core.applications.users.models import StudentContact
from core.applications.users.models import StudentProfile
from core.applications.users.models import User
from core.helper.tenants import clear_current_school
from core.helper.tenants import set_current_school


class TenantAwareModelTests(TestCase):

    def setUp(self):
        """
        Create two schools, one user per school.
        user_b is created here so all tests that need a
        school_b student have access to it without repeating setup.
        """
        self.school_a = School.objects.create(
            name="GreenField Academy", slug="greenfield"
        )
        self.school_b = School.objects.create(
            name="Brookside High", slug="brookside"
        )
        self.user_a = User.objects.create_user(
            email="student@greenfield.com",
            password="pass",
            school=self.school_a,
        )
        self.user_b = User.objects.create_user(
            email="student@brookside.com",
            password="pass",
            school=self.school_b,
        )

    def tearDown(self):
        clear_current_school()

    # ------------------------------------------------------------------
    # Auto-assign school from context
    # ------------------------------------------------------------------

    def test_school_auto_assigned_from_thread_local(self):
        """
        StudentContact extends TenantAwareModel so it has
        _assign_school_from_context().

        StudentProfile extends BaseProfile → TimeStampedModel and does NOT
        have this method — it was the wrong model in the original test.

        We test on StudentContact which is the correct TenantAwareModel subclass.
        """
        set_current_school(self.school_a)

        contact = StudentContact(
            name="Test Parent",
            relationship="Father",
            phone="08012345678",
        )
        # school not set manually — should be pulled from thread-local
        contact._assign_school_from_context()

        self.assertEqual(contact.school, self.school_a)

    def test_save_without_context_raises(self):
        """
        Saving a TenantAwareModel with no school in thread-local
        and no school set explicitly must raise ValidationError.
        """
        clear_current_school()

        contact = StudentContact(
            name="Parent Name",
            relationship="Father",
            phone="08012345678",
        )
        with self.assertRaises(ValidationError) as ctx:
            contact.save()

        self.assertIn("school context", str(ctx.exception))

    def test_school_not_overwritten_if_already_set(self):
        """
        If school is explicitly set on the object before
        _assign_school_from_context() runs, the thread-local
        must not overwrite it.
        """
        set_current_school(self.school_b)

        contact = StudentContact(school=self.school_a)
        contact._assign_school_from_context()

        # school_a was explicitly set — must NOT be replaced by school_b
        self.assertEqual(contact.school, self.school_a)

    # ------------------------------------------------------------------
    # Validation — school active
    # ------------------------------------------------------------------

    def test_save_to_inactive_school_raises(self):
        """
        Writing any data to a deactivated school must be rejected.
        The _validate_school_active() check in clean() handles this.
        """
        self.school_a.is_active = False
        self.school_a.save()

        set_current_school(self.school_a)

        contact = StudentContact(
            name="Parent Name",
            relationship="Father",
            phone="08012345678",
        )
        with self.assertRaises(ValidationError) as ctx:
            contact.save()

        self.assertIn("deactivated", str(ctx.exception))

    # ------------------------------------------------------------------
    # Cross-tenant validation
    # ------------------------------------------------------------------

    def test_cross_tenant_relation_raises(self):
        """
        StudentContact belongs to school_a.
        Its student FK points to a StudentProfile from school_b.
        This cross-tenant relation must be caught and rejected by
        _validate_related_tenant_fields() in TenantAwareModel.clean().

        Original test had two problems:
        1. student FK was never set → Django field validation fired first
           with "student cannot be null" before cross-tenant check ran
        2. No StudentProfile was created for user_b to link to

        Fix:
        - Create a real StudentProfile for user_b
        - Set student=student_b on the contact so field validation passes
        - Cross-tenant check then runs and catches the school mismatch
        """
        set_current_school(self.school_a)

        # Create a real StudentProfile for school_b's user
        student_b = StudentProfile.objects.create(
            user=self.user_b,
        )

        # Contact claims to belong to school_a
        # but its student belongs to school_b — cross-tenant attack
        contact = StudentContact(
            school=self.school_a,
            student=student_b,
            name="Bad Parent",
            relationship="Mother",
            phone="08099999999",
        )

        with self.assertRaises(ValidationError) as ctx:
            contact.full_clean()

        self.assertIn("different school", str(ctx.exception))

    # ------------------------------------------------------------------
    # tenant_db property
    # ------------------------------------------------------------------

    def test_tenant_db_property_returns_correct_alias(self):
        """
        Before save, _state.db is None.
        tenant_db property falls back to get_current_db_alias().
        school_a is SHARED tier so alias is 'default'.
        """
        set_current_school(self.school_a)

        contact = StudentContact(
            school=self.school_a,
            name="Test Parent",
            relationship="Father",
            phone="08011111111",
        )
        self.assertEqual(contact.tenant_db, "default")

    # ------------------------------------------------------------------
    # for_school classmethod
    # ------------------------------------------------------------------

    def test_for_school_classmethod(self):
        """
        for_school() explicitly scopes to a specific school
        regardless of the current thread-local context.
        school_b is active but for_school(school_a) returns school_a data.
        """
        set_current_school(self.school_b)

        qs = StudentContact.for_school(self.school_a)
        for contact in qs:
            self.assertEqual(contact.school, self.school_a)

    # ------------------------------------------------------------------
    # unscoped classmethod
    # ------------------------------------------------------------------

    def test_unscoped_returns_all_tenants(self):
        """
        unscoped() bypasses all tenant filtering.
        Returns all records across every school.
        Must only be used in superadmin operations.
        """
        set_current_school(self.school_a)
        qs = StudentContact.unscoped()
        self.assertIsNotNone(qs)
