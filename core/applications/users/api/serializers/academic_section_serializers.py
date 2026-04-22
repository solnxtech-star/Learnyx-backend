import re
from datetime import datetime
from datetime import timedelta

from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.applications.academics.models import AcademicSession
from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import Subject
from core.applications.academics.models import TeachingAssignment
from core.applications.academics.models import TermPeriod
from core.applications.users.models import TeacherProfile
from core.applications.users.models import User

# ============================================================================
# Academic Session Serializer
# ============================================================================


class AcademicSessionSerializer(serializers.ModelSerializer):
    """
    Tenant-aware serializer for AcademicSession.

    Business Rules:
    - Unique session name per school.
    - Only one active session per school.
    - Session name format YYYY/YYYY or YYYY-YYYY.
    - End date must be after start date.
    - School is derived from authenticated user.
    """

    school_name = serializers.CharField(source="school.name", read_only=True)
    term_count = serializers.SerializerMethodField()

    class Meta:
        model = AcademicSession
        fields = [
            "id",
            "school",
            "school_name",
            "name",
            "start_date",
            "end_date",
            "is_active",
            "term_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "school"]

    # -----------------------------------------------------
    # Derived Fields
    # -----------------------------------------------------
    def get_term_count(self, obj):
        return obj.terms.count()

    # -----------------------------------------------------
    # Field-level validation
    # -----------------------------------------------------
    def validate_name(self, value):
        pattern = r"^\d{4}[/-]\d{4}$"
        if not re.match(pattern, value):
            raise serializers.ValidationError(
                _("Session must follow YYYY/YYYY or YYYY-YYYY.")
            )
        return value

    # -----------------------------------------------------
    # Global validation
    # -----------------------------------------------------
    def validate(self, attrs):
        school = self.instance.school if self.instance else self._get_school()
        name = attrs.get("name", getattr(self.instance, "name", None))
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))

        # Tenant-aware uniqueness check
        if name:
            qs = AcademicSession.objects.for_school(school).filter(name=name)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": _("An academic session with this name already exists.")}
                )

        # Validate date order
        if start_date and end_date and end_date <= start_date:
            raise serializers.ValidationError(
                {"end_date": _("End date must be after start date.")}
            )

        return attrs

    # -----------------------------------------------------
    # Helper to get school from request
    # -----------------------------------------------------
    def _get_school(self):
        request = self.context.get("request")
        if not request or not getattr(request.user, "school", None):
            raise serializers.ValidationError(_("School context missing."))
        return request.user.school

    # -----------------------------------------------------
    # Create
    # -----------------------------------------------------
    @transaction.atomic
    def create(self, validated_data):
        school = self._get_school()
        validated_data["school"] = school

        # Ensure only one active session per school
        if validated_data.get("is_active"):
            AcademicSession.objects.for_school(school).update(is_active=False)

        return super().create(validated_data)

    # -----------------------------------------------------
    # Update
    # -----------------------------------------------------
    @transaction.atomic
    def update(self, instance, validated_data):
        if validated_data.get("is_active"):
            AcademicSession.objects.for_school(instance.school).exclude(id=instance.id).update(
                is_active=False
            )
        return super().update(instance, validated_data)


# =========================================================
# Open / Close Session Serializers
# =========================================================
class OpenAcademicSessionSerializer(serializers.Serializer):
    """
    Tenant-aware serializer for opening an academic session.

    Rules:
    - Deactivates all other sessions for the same school.
    - Cannot open sessions belonging to another school.
    """

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "school"):
            raise serializers.ValidationError(_("Authenticated user must belong to a school."))

        user_school = request.user.school

        if instance.school != user_school:
            raise serializers.ValidationError(_("Cannot open a session for another school."))

        # Deactivate other sessions for the same school
        AcademicSession.objects.for_school(user_school).exclude(id=instance.id).update(
            is_active=False
        )

        instance.is_active = True
        instance.save(update_fields=["is_active"])
        return instance


class CloseAcademicSessionSerializer(serializers.Serializer):
    """
    Tenant-aware serializer for closing an academic session.

    Rules:
    - Only active sessions can be closed.
    - Cannot close sessions belonging to another school.
    """

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "school"):
            raise serializers.ValidationError(_("Authenticated user must belong to a school."))

        user_school = request.user.school

        if instance.school != user_school:
            raise serializers.ValidationError(_("Cannot close a session for another school."))

        if not instance.is_active:
            raise serializers.ValidationError(_("Session is already closed."))

        instance.is_active = False
        instance.save(update_fields=["is_active"])
        return instance
# ============================================================================
# Academic Term Serializer
# ============================================================================

class TermPeriodSerializer(serializers.ModelSerializer):
    """
    Serializer for individual periods within an academic term.

    Responsibilities:
    - Supports Half-Term, Exam, Holiday, or custom periods.
    - Validates start and end dates.
    - Ensures periods fall within the parent term.
    - Prevents overlapping periods within the same term.
    - Enforces tenant (school) scope.
    - Enforces single active period per term on activation.
    """

    class Meta:
        model = TermPeriod
        fields = [
            "id",
            "term",
            "name",
            "period_type",
            "is_active",
            "start_date",
            "end_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def _get_school(self):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        if not school:
            raise serializers.ValidationError(_("School context missing."))
        return school

    def validate(self, data):
        term = data.get("term") or getattr(self.instance, "term", None)
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        if not term:
            raise serializers.ValidationError(_("Term is required for a period."))

        school = self._get_school()
        if term.school != school:
            raise serializers.ValidationError(_("Cross-school access denied."))

        if start_date and end_date:
            if start_date > end_date:
                raise serializers.ValidationError(
                    _("Period start_date cannot be after end_date.")
                )
            if start_date < term.start_date or end_date > term.end_date:
                raise serializers.ValidationError(
                    _("Period must fall within the term's start and end dates.")
                )

            # Overlap check against siblings
            existing_periods = term.periods.exclude(
                pk=getattr(self.instance, "pk", None)
            )
            for ep in existing_periods:
                if not (end_date < ep.start_date or start_date > ep.end_date):
                    raise serializers.ValidationError(
                        _("Period dates cannot overlap with existing period '%s'.") % ep.name
                    )

        return data

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        On activation, deactivate all sibling periods in the same term
        before saving — ensuring only one active period per term at all times.
        """
        activating = validated_data.get("is_active", False)

        if activating:
            instance.term.periods.exclude(pk=instance.pk).update(is_active=False)

        return super().update(instance, validated_data)


# ============================================================================
# Helpers (module-level)
# ============================================================================

# ============================================================================
# Helpers (module-level)
# ============================================================================

TERM_NAMES = {1: "First Term", 2: "Second Term", 3: "Third Term"}


def determine_term_type(term_number: int) -> str:
    """
    All three terms are full terms. The assessment stage (HALF_TERM vs END_OF_TERM)
    is determined at score computation time, not by term number.
    term_type on AcademicTerm is descriptive only.
    """
    return "FULL_TERM"


def auto_generate_periods(school, term, activate_first: bool = True) -> list:
    """
    Auto-generate four TermPeriods for a term:
    - First Half:     teaching period before the break      → is_active=True (default)
    - Mid-Term Break: half-term holiday                     → is_active=False
    - Second Half:    teaching period after the break       → is_active=False
    - Exams:          exam period at end of term            → is_active=False

    Falls back to two periods if the term is too short for four.

    Args:
        activate_first: if True, marks the first period as active.
                        Pass False when bulk-creating terms that are not yet active.

    Returns:
        list of unsaved TermPeriod objects.
    """
    start_date = term.start_date
    end_date = term.end_date

    mid_date = start_date + (end_date - start_date) // 2
    break_start = mid_date + timedelta(days=1)
    break_end = break_start + timedelta(days=6)
    second_half_start = break_end + timedelta(days=1)
    exam_start = end_date - timedelta(days=13)
    second_half_end = exam_start - timedelta(days=1)

    # Safety fallback for very short terms
    if second_half_end <= second_half_start or exam_start >= end_date:
        return [
            TermPeriod(
                school=school, term=term,
                name="First Half",
                period_type=TermPeriod.PeriodType.OTHER,
                start_date=start_date,
                end_date=mid_date,
                is_active=activate_first,
            ),
            TermPeriod(
                school=school, term=term,
                name="Second Half",
                period_type=TermPeriod.PeriodType.OTHER,
                start_date=mid_date + timedelta(days=1),
                end_date=end_date,
                is_active=False,
            ),
        ]

    return [
        TermPeriod(
            school=school, term=term,
            name="First Half",
            period_type=TermPeriod.PeriodType.OTHER,
            start_date=start_date,
            end_date=mid_date,
            is_active=activate_first,  # first period open by default
        ),
        TermPeriod(
            school=school, term=term,
            name="Mid-Term Break",
            period_type=TermPeriod.PeriodType.HALF_TERM,
            start_date=break_start,
            end_date=break_end,
            is_active=False,
        ),
        TermPeriod(
            school=school, term=term,
            name="Second Half",
            period_type=TermPeriod.PeriodType.OTHER,
            start_date=second_half_start,
            end_date=second_half_end,
            is_active=False,
        ),
        TermPeriod(
            school=school, term=term,
            name="Exams",
            period_type=TermPeriod.PeriodType.EXAM,
            start_date=exam_start,
            end_date=end_date,
            is_active=False,
        ),
    ]


# ============================================================================
# AcademicTerm Serializer
# ============================================================================

class AcademicTermSerializer(serializers.ModelSerializer):
    """
    Tenant-aware serializer for Academic Terms.

    Responsibilities:
    - Supports First, Second, Third Terms.
    - name is a read-only property derived from term_number — never written to DB.
    - term_type is always FULL_TERM — stage drives scoring at computation time.
    - Enforces single active term per session and tenant.
    - Prevents activation under inactive sessions.
    - Supports nested TermPeriods (optional user-provided periods).
    - Auto-generates four periods if none provided.
    - Ensures term dates fall within session and periods fall within term.
    - Enforces single active period per term at all times.
    """

    session_name = serializers.CharField(source="session.name", read_only=True)
    is_current = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    periods = TermPeriodSerializer(many=True, required=False)

    class Meta:
        model = AcademicTerm
        fields = [
            "id",
            "session",
            "session_name",
            "name",
            "term_number",
            "term_type",
            "is_active",
            "is_current",
            "start_date",
            "end_date",
            "periods",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "term_type", "created_at", "updated_at"]

    # -----------------------
    # Tenant helpers
    # -----------------------

    def _get_school(self):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        if not school:
            raise serializers.ValidationError(_("School context missing."))
        return school

    def _tenant_qs(self):
        return AcademicTerm.objects.for_school(self._get_school())

    # -----------------------
    # Read-only computed fields
    # -----------------------

    def get_name(self, obj):
        return obj.name

    def get_is_current(self, obj):
        return obj.is_active and obj.session.is_active

    # -----------------------
    # Field-level validation
    # -----------------------

    def validate_term_number(self, value):
        if value not in TERM_NAMES:
            raise serializers.ValidationError(_("term_number must be 1, 2, or 3."))
        return value

    # -----------------------
    # Object-level validation
    # -----------------------

    def validate(self, attrs):
        school = self._get_school()
        session = attrs.get("session") or getattr(self.instance, "session", None)
        term_number = attrs.get("term_number") or getattr(self.instance, "term_number", None)
        start_date = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end_date = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        periods = attrs.get("periods", [])

        if session and session.school != school:
            raise serializers.ValidationError(_("Cross-school access denied."))

        # Uniqueness of term_number within session
        if session and term_number:
            qs = self._tenant_qs().filter(session=session, term_number=term_number)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    _("Term number '%s' already exists in this session.") % term_number
                )

        # Term date validation against session bounds
        if start_date and end_date:
            if end_date <= start_date:
                raise serializers.ValidationError(_("Term end_date must be after start_date."))
            if session.start_date and start_date < session.start_date:
                raise serializers.ValidationError(
                    _("Term cannot start before session start_date.")
                )
            if session.end_date and end_date > session.end_date:
                raise serializers.ValidationError(
                    _("Term cannot end after session end_date.")
                )

        # Validate nested periods if provided
        if periods:
            # Enforce only one active period in the provided list
            active_periods = [p for p in periods if p.get("is_active", False)]
            if len(active_periods) > 1:
                raise serializers.ValidationError(
                    _("Only one period can be active at a time within a term.")
                )

            sorted_periods = sorted(
                periods, key=lambda p: p.get("start_date") or timezone.now().date()
            )
            for i, p in enumerate(sorted_periods):
                p_start = p.get("start_date")
                p_end = p.get("end_date")

                if p_start and p_end:
                    if p_end <= p_start:
                        raise serializers.ValidationError(
                            _("Each period's end_date must be after its start_date.")
                        )
                    if start_date and (p_start < start_date or p_end > end_date):
                        raise serializers.ValidationError(
                            _("All periods must fall within the term dates.")
                        )

                if i > 0:
                    prev = sorted_periods[i - 1]
                    if p_start and prev.get("end_date") and p_start <= prev["end_date"]:
                        raise serializers.ValidationError(
                            _("Periods cannot overlap within a term.")
                        )

        return attrs

    # -----------------------
    # Create / Update
    # -----------------------

    @transaction.atomic
    def create(self, validated_data):
        school = self._get_school()
        validated_data["school"] = school
        validated_data.pop("name", None)
        periods_data = validated_data.pop("periods", [])
        term_number = validated_data.get("term_number")
        is_active = validated_data.get("is_active", False)

        validated_data["term_type"] = determine_term_type(term_number)

        # Deactivate sibling terms if this one is being activated
        if is_active and validated_data.get("session"):
            self._tenant_qs().filter(
                session=validated_data["session"]
            ).update(is_active=False)

        term = super().create(validated_data)

        if periods_data:
            # User provided periods — respect their is_active flags,
            # but ensure no more than one is active
            TermPeriod.objects.bulk_create([
                TermPeriod(school=school, term=term, **p) for p in periods_data
            ])
        elif term.start_date and term.end_date:
            # Auto-generate periods — only activate first period
            # if the term itself is being activated
            TermPeriod.objects.bulk_create(
                auto_generate_periods(school, term, activate_first=is_active)
            )

        return term

    @transaction.atomic
    def update(self, instance, validated_data):
        school = self._get_school()
        validated_data.pop("name", None)
        periods_data = validated_data.pop("periods", None)
        term_number = validated_data.get("term_number") or instance.term_number
        is_active = validated_data.get("is_active", instance.is_active)

        # Block activation under inactive session
        if validated_data.get("is_active") and not instance.session.is_active:
            raise serializers.ValidationError(
                _("Cannot activate term under an inactive session.")
            )

        # Deactivate sibling terms if activating this one
        if validated_data.get("is_active"):
            self._tenant_qs().filter(
                session=instance.session
            ).exclude(pk=instance.pk).update(is_active=False)

        # If deactivating the term, also deactivate all its periods
        if not is_active and instance.is_active:
            instance.periods.update(is_active=False)

        validated_data["term_type"] = determine_term_type(term_number)

        term = super().update(instance, validated_data)

        # Replace periods if explicitly provided
        if periods_data is not None:
            term.periods.all().delete()
            TermPeriod.objects.bulk_create([
                TermPeriod(school=school, term=term, **p) for p in periods_data
            ])

        return term


# ============================================================================
# Bulk AcademicTerm Serializer
# ============================================================================

class BulkTermItemSerializer(serializers.Serializer):
    """Validates a single term entry within a bulk creation request."""

    term_number = serializers.IntegerField(min_value=1)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    is_active = serializers.BooleanField(default=False)

    def validate_term_number(self, value):
        if value not in TERM_NAMES:
            raise serializers.ValidationError(_("term_number must be 1, 2, or 3."))
        return value

    def validate(self, attrs):
        if attrs["end_date"] <= attrs["start_date"]:
            raise serializers.ValidationError(_("end_date must be after start_date."))
        attrs["term_type"] = determine_term_type(attrs["term_number"])
        return attrs


class BulkAcademicTermSerializer(serializers.Serializer):
    """
    Serializer for bulk creation of academic terms.

    Responsibilities:
    - Validates tenant scope and active session.
    - Prevents duplicate term_numbers in payload and DB.
    - Ensures each term's dates fall within the session bounds.
    - Ensures only one term in the payload is marked active.
    - Auto-generates periods per term; only activates first period
      on the active term.
    """

    session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.all())
    terms = BulkTermItemSerializer(many=True)

    def _get_school(self):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        if not school:
            raise serializers.ValidationError(_("School context missing."))
        return school

    def validate_terms(self, terms):
        if not terms:
            raise serializers.ValidationError(_("At least one term is required."))

        term_numbers = [t["term_number"] for t in terms]
        if len(term_numbers) != len(set(term_numbers)):
            raise serializers.ValidationError(_("Duplicate term_number detected in payload."))

        # Enforce only one active term in the payload
        active_terms = [t for t in terms if t.get("is_active", False)]
        if len(active_terms) > 1:
            raise serializers.ValidationError(
                _("Only one term can be marked as active in a bulk creation request.")
            )

        return terms

    def validate(self, data):
        school = self._get_school()
        session = data["session"]
        terms = data["terms"]

        if session.school != school:
            raise serializers.ValidationError(_("Cross-school access denied."))

        if not session.is_active:
            raise serializers.ValidationError(
                _("Cannot create terms under an inactive session.")
            )

        term_numbers = [t["term_number"] for t in terms]
        existing_numbers = set(
            AcademicTerm.objects.for_school(school)
            .filter(session=session)
            .values_list("term_number", flat=True)
        )
        conflicting = [n for n in term_numbers if n in existing_numbers]
        if conflicting:
            raise serializers.ValidationError(
                _("Term number(s) %s already exist in this session.") % conflicting
            )

        for term in terms:
            start = term["start_date"]
            end = term["end_date"]
            if session.start_date and start < session.start_date:
                raise serializers.ValidationError(
                    _("Term %s cannot start before session start_date.") % term["term_number"]
                )
            if session.end_date and end > session.end_date:
                raise serializers.ValidationError(
                    _("Term %s cannot end after session end_date.") % term["term_number"]
                )

        return data

    # -----------------------
    # Create / Update
    # -----------------------

    @transaction.atomic
    def create(self, validated_data):
        school = self._get_school()
        validated_data["school"] = school
        validated_data.pop("name", None)  # name is a @property — not a DB field
        periods_data = validated_data.pop("periods", [])
        term_number = validated_data.get("term_number")

        # Always FULL_TERM — stage drives scoring, not term_type
        validated_data["term_type"] = determine_term_type(term_number)

        # Deactivate other active terms in this session
        if validated_data.get("is_active") and validated_data.get("session"):
            self._tenant_qs().filter(session=validated_data["session"]).update(is_active=False)

        term = super().create(validated_data)

        # Create periods — user-provided or auto-generated
        if periods_data:
            TermPeriod.objects.bulk_create([
                TermPeriod(school=school, term=term, **p) for p in periods_data
            ])
        elif term.start_date and term.end_date:
            TermPeriod.objects.bulk_create(auto_generate_periods(school, term))

        return term

    @transaction.atomic
    def update(self, instance, validated_data):
        school = self._get_school()
        validated_data.pop("name", None)  # name is a @property — not a DB field
        periods_data = validated_data.pop("periods", None)
        term_number = validated_data.get("term_number") or instance.term_number

        # Block activation under inactive session
        if validated_data.get("is_active") and not instance.session.is_active:
            raise serializers.ValidationError(
                _("Cannot activate term under an inactive session.")
            )

        # Deactivate sibling terms if activating this one
        if validated_data.get("is_active") and instance.session:
            self._tenant_qs().filter(
                session=instance.session
            ).exclude(pk=instance.pk).update(is_active=False)

        # Always FULL_TERM
        validated_data["term_type"] = determine_term_type(term_number)

        term = super().update(instance, validated_data)

        # Replace periods if explicitly provided
        if periods_data is not None:
            term.periods.all().delete()
            TermPeriod.objects.bulk_create([
                TermPeriod(school=school, term=term, **p) for p in periods_data
            ])

        return term


# ============================================================================
# Academic Structure Setup Serializer (Bulk Setup)
# ============================================================================


class AcademicStructureSetupSerializer(serializers.Serializer):
    """
    Enforces default school structure:

    - Single academic session
    - Exactly three terms
    """

    session_name = serializers.CharField(max_length=20)
    automatic_activation = serializers.BooleanField(default=True)

    STANDARD_TERMS = ["First Term", "Second Term", "Third Term"]

    def _get_school(self):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "school"):
            raise serializers.ValidationError(_("School context missing."))
        return request.user.school

    @transaction.atomic
    def create(self, validated_data):
        school = self._get_school()

        if validated_data.get("automatic_activation"):
            AcademicSession.objects.filter(school=school).update(is_active=False)

        session = AcademicSession.objects.create(
            school=school,
            name=validated_data["session_name"],
            is_active=validated_data["automatic_activation"],
        )

        terms = []
        for index, name in enumerate(self.STANDARD_TERMS):
            terms.append(
                AcademicTerm.objects.create(
                    session=session,
                    name=name,
                    term_type="FULL_TERM",
                    is_active=validated_data["automatic_activation"] and index == 0,
                ),
            )

        return {"session": session, "terms": terms}


# ============================================================================
# Subject Serializer
# ============================================================================


class SubjectSerializer(serializers.ModelSerializer):
    """
    Tenant-aware serializer for Subjects.

    Responsibilities:
    - Automatically assigns the authenticated user's school.
    - Normalizes subject name and code (title-case / upper-case).
    - Enforces classroom ownership and school-level isolation.
    - Prevents duplicates of active subject names and codes per school.
    - Supports soft deletes (is_active=True only).
    - Handles creation and update with transactional safety.
    """

    school_name = serializers.CharField(source="school.name", read_only=True)
    is_mandatory = serializers.BooleanField(required=False)
    credit_hour = serializers.IntegerField(min_value=1, required=False)
    class_rooms = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=ClassRoom.objects.all(),
        required=False,
    )

    class Meta:
        model = Subject
        fields = [
            "id",
            "school",
            "school_name",
            "name",
            "code",
            "description",
            "is_mandatory",
            "credit_hour",
            "class_rooms",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "school", "created_at", "updated_at"]

    # -----------------------
    # Tenant helpers
    # -----------------------
    def _get_school(self):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        if not school:
            raise serializers.ValidationError(_("School context missing."))
        return school

    def _tenant_qs(self):
        """Return tenant-scoped queryset for this model."""
        return Subject.objects.for_school(self._get_school())

    # -----------------------
    # Field-level validation
    # -----------------------
    def validate_name(self, value):
        normalized = value.strip().title()
        if len(normalized) < 3:
            raise serializers.ValidationError(_("Subject name is too short."))

        qs = self._tenant_qs().filter(name__iexact=normalized, is_active=True)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                _("A subject with this name already exists in your school.")
            )
        return normalized

    def validate_code(self, value):
        normalized = value.strip().upper()
        if len(normalized) < 3:
            raise serializers.ValidationError(_("Subject code is too short."))

        qs = self._tenant_qs().filter(code=normalized, is_active=True)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                _("A subject with this code already exists in your school.")
            )
        return normalized

    def validate_credit_hour(self, value):
        if value < 1:
            raise serializers.ValidationError(_("Credit hour must be at least 1."))
        return value

    def validate_class_rooms(self, value):
        school = self._get_school()
        for classroom in value:
            if classroom.school_id != school.id:
                raise serializers.ValidationError(
                    _("Classroom '%s' does not belong to your school.") % classroom
                )
        return value

    # -----------------------
    # Object-level validation
    # -----------------------
    def validate(self, attrs):
        name = attrs.get("name", getattr(self.instance, "name", None))
        code = attrs.get("code", getattr(self.instance, "code", None))
        if not name or not code:
            return attrs

        qs = self._tenant_qs().filter(name__iexact=name, code=code, is_active=True)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                _("A subject with this name and code already exists in your school.")
            )
        return attrs

    # -----------------------
    # Create / Update
    # -----------------------
    @transaction.atomic
    def create(self, validated_data):
        class_rooms = validated_data.pop("class_rooms", [])
        validated_data["school"] = self._get_school()

        try:
            subject = super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError(
                _("A subject with this name or code already exists in your school."),
            )

        if class_rooms:
            subject.class_rooms.set(class_rooms)
        return subject

    @transaction.atomic
    def update(self, instance, validated_data):
        class_rooms = validated_data.pop("class_rooms", None)

        try:
            subject = super().update(instance, validated_data)
        except IntegrityError:
            raise serializers.ValidationError(
                _("A subject with this name or code already exists in your school."),
            )

        if class_rooms is not None:
            subject.class_rooms.set(class_rooms)
        return subject
# ============================================================================

class TeacherUserSerializer(serializers.ModelSerializer):
    school = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "phone_number",
            "role",
            "is_verified",
            "date_joined",
            "last_login",
            "school",
        ]
        read_only_fields = fields

    def get_school(self, obj):
        if not obj.school:
            return None
        return {
            "id": str(obj.school.id),
            "name": obj.school.name,
        }

class TeacherListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer used for listing teacher profiles.

    Purpose:
        - Returns a summarized teacher record.
        - Used in admin/management teacher listing page.

    Includes:
        - Email (from related User model)
        - Qualification
        - Specialization
        - Department
        - Staff ID
    """
    email = serializers.EmailField(source="user.email")

    class Meta:
        model = TeacherProfile
        fields = [
            "id",
            "email",
            "qualification",
            "specialization",
            "department",
            "staff_id",
        ]


class TeacherDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for retrieving a single teacher profile.

    Exposes:
        - Nested user information
        - Professional profile data
        - Structured classroom + subject assignments
    """

    user = TeacherUserSerializer(read_only=True)
    teaching_assignments = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TeacherProfile
        fields = [
            "id",
            "user",
            "qualification",
            "specialization",
            "department",
            "staff_id",
            "teaching_assignments",
        ]

    def get_teaching_assignments(self, obj):
        """
        Return structured classroom + subject assignments.

        NOTE:
        Assumes queryset uses proper select_related/prefetch_related
        to avoid N+1 queries.
        """

        assignments = obj.teaching_assignments.all()

        return [
            {
                "classroom": {
                    "id": str(a.classroom.id),
                    "name": f"{a.classroom.academic_class}{a.classroom.arm}",
                    "level": a.classroom.academic_class,
                    "arm": a.classroom.arm,
                    "school": {
                        "id": str(a.classroom.school.id),
                        "name": a.classroom.school.name,
                    },
                },
                "subject": {
                    "id": str(a.subject.id),
                    "name": a.subject.name,
                    "code": getattr(a.subject, "code", None),
                    "school": {
                        "id": str(a.subject.school.id),
                        "name": a.subject.school.name,
                    },
                },
            }
            for a in assignments
        ]

class ClassroomSubjectAssignmentSerializer(serializers.Serializer):
    """Serializer for assigning subjects to a teacher for a specific classroom."""
    classroom_id = serializers.CharField()
    subject_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )

class AdminAssignClassroomsAndSubjectsSerializer(serializers.Serializer):
    """
    Admin-only serializer to assign subjects per classroom to a teacher.

    Behavior:
        - Accepts structured assignments per classroom.
        - Replaces ALL existing teacher assignments.
        - Prevents cross-class subject leakage.
        - Ensures strict school-level validation.
        - Prevents duplicates at all levels.
        - Fully transactional.
    """

    assignments = ClassroomSubjectAssignmentSerializer(many=True)

    def validate(self, data):
        school = self.context["request"].user.school
        assignments = data["assignments"]

        if not assignments:
            msg = "At least one assignment is required."
            raise serializers.ValidationError(msg)

        seen_classrooms = set()
        all_subject_ids = set()

        for item in assignments:
            classroom_id = item["classroom_id"]
            subject_ids = item["subject_ids"]

            # Prevent duplicate classrooms
            if classroom_id in seen_classrooms:
                msg = f"Duplicate classroom assignment detected: {classroom_id}"
                raise serializers.ValidationError(
                    msg,
                )
            seen_classrooms.add(classroom_id)

            # Prevent empty subject list (extra safety)
            if not subject_ids:
                msg = f"Classroom {classroom_id} must have at least one subject."
                raise serializers.ValidationError(
                    msg,
                )

            # Prevent duplicate subjects per classroom
            if len(subject_ids) != len(set(subject_ids)):
                msg = f"Duplicate subjects in classroom {classroom_id}."
                raise serializers.ValidationError(
                    msg
                )

            all_subject_ids.update(subject_ids)

        # Validate classrooms belong to school
        valid_classrooms = set(
            ClassRoom.objects.filter(id__in=seen_classrooms, school=school)
            .values_list("id", flat=True)
        )

        if seen_classrooms != valid_classrooms:
            msg = "Some classrooms do not exist or do not belong to your school."
            raise serializers.ValidationError(
                msg,
            )

        #  Validate subjects belong to school
        valid_subjects = set(
            Subject.objects.filter(id__in=all_subject_ids, school=school)
            .values_list("id", flat=True)
        )

        if all_subject_ids != valid_subjects:
            msg = "Some subjects do not exist or do not belong to your school."
            raise serializers.ValidationError(
                msg,
            )

        return data

    @transaction.atomic
    def save(self):
        teacher = self.context["teacher"]
        assignments_data = self.validated_data["assignments"]

        # ✅ Flatten sets for M2M
        classroom_ids = {item["classroom_id"] for item in assignments_data}
        subject_ids = {
            subject_id
            for item in assignments_data
            for subject_id in item["subject_ids"]
        }

        # ✅ Update M2M (no need for teacher.save())
        teacher.classrooms.set(classroom_ids)
        teacher.subjects.set(subject_ids)

        # ✅ Clean reset (safe + predictable)
        TeachingAssignment.objects.filter(teacher=teacher).delete()

        # ✅ Build exact assignments (no cross combinations)
        new_assignments = [
            TeachingAssignment(
                teacher=teacher,
                classroom_id=item["classroom_id"],
                subject_id=subject_id,
            )
            for item in assignments_data
            for subject_id in item["subject_ids"]
        ]

        # ✅ Safe bulk insert
        TeachingAssignment.objects.bulk_create(
            new_assignments,
            ignore_conflicts=True,
        )

        return teacher




class ClassroomSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassRoom
        fields = ["id", "academic_class"]



class TeachingAssignmentNestedSerializer(serializers.ModelSerializer):
    classroom = serializers.StringRelatedField()
    subject = serializers.StringRelatedField()


    class Meta:
        model = TeachingAssignment
        fields = ["classroom", "subject"]


class TeacherListWithAssignmentsSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name")
    user_email = serializers.EmailField(source="user.email")
    assignments = TeachingAssignmentNestedSerializer(
        source="teaching_assignments", many=True, read_only=True
    )

    class Meta:
        model = TeacherProfile
        fields = [
            "id",
            "user_name",
            "user_email",
            "staff_id",
            "assignments",  # replaces classrooms + subjects
        ]


class ClassRoomListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        school = self.context["school"]

        instances = [
            ClassRoom(school=school, **item)
            for item in validated_data
        ]

        return ClassRoom.objects.bulk_create(instances)
