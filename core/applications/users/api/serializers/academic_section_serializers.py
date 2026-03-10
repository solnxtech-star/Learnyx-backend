import re
from datetime import timedelta

from django.db import IntegrityError
from django.db import transaction
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
    - Ensures periods fall within the parent term and tenant scope.
    """

    class Meta:
        model = TermPeriod
        fields = [
            "id",
            "term",
            "name",
            "period_type",
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

        if start_date > end_date:
            raise serializers.ValidationError(_("start_date cannot be after end_date."))

        if start_date < term.start_date or end_date > term.end_date:
            raise serializers.ValidationError(_("Period must fall within the term start and end dates."))

        return data


# ============================================================================
# AcademicTerm Serializer
# ============================================================================
class AcademicTermSerializer(serializers.ModelSerializer):
    """
    Tenant-aware serializer for Academic Terms.

    Responsibilities:
    - Supports First, Second, Third Terms.
    - Auto-determines term_type if not explicitly provided.
    - Enforces single active term per session and tenant.
    - Prevents activation under inactive sessions.
    - Supports nested TermPeriods (optional user-provided periods).
    - Auto-generates First Half / Second Half periods if none are provided.
    """

    session_name = serializers.CharField(source="session.name", read_only=True)
    is_current = serializers.SerializerMethodField()
    periods = TermPeriodSerializer(many=True, required=False)
    STANDARD_TERMS = ["First Term", "Second Term", "Third Term"]

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
        read_only_fields = ["id", "created_at", "updated_at"]

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
    # Field & object validation
    # -----------------------
    def get_is_current(self, obj):
        return obj.is_active and obj.session.is_active

    def validate(self, attrs):
        school = self._get_school()
        session = attrs.get("session") or getattr(self.instance, "session", None)
        term_number = attrs.get("term_number") or getattr(self.instance, "term_number", None)
        name = attrs.get("name") or getattr(self.instance, "name", None)

        if session and session.school != school:
            raise serializers.ValidationError(_("Cross-school access denied."))

        if name and name not in self.STANDARD_TERMS:
            raise serializers.ValidationError(
                _("Allowed terms are: %s") % ", ".join(self.STANDARD_TERMS)
            )

        if session and term_number:
            qs = self._tenant_qs().filter(session=session, term_number=term_number)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    _("Term number '%s' already exists in this session.") % term_number
                )

        return attrs

    def _determine_term_type(self, term_number: int):
        if term_number in (1, 2):
            return "HALF_TERM"
        if term_number == 3:
            return "END_OF_TERM"
        return "FULL_TERM"

    # -----------------------
    # Create / Update
    # -----------------------
    @transaction.atomic
    def create(self, validated_data):
        school = self._get_school()
        validated_data["school"] = school
        periods_data = validated_data.pop("periods", [])
        term_number = validated_data.get("term_number")

        if not validated_data.get("term_type") and term_number:
            validated_data["term_type"] = self._determine_term_type(term_number)

        # Deactivate other active terms
        if validated_data.get("is_active") and validated_data.get("session"):
            self._tenant_qs().filter(session=validated_data["session"]).update(is_active=False)

        term = super().create(validated_data)

        # Handle periods
        if periods_data:
            periods = [TermPeriod(school=school, term=term, **p) for p in periods_data]
            TermPeriod.objects.bulk_create(periods)
        else:
            start_date = term.start_date
            end_date = term.end_date
            if start_date and end_date:
                mid_date = start_date + (end_date - start_date) // 2
                TermPeriod.objects.bulk_create([
                    TermPeriod(
                        school=school,
                        term=term,
                        name="First Half",
                        period_type=TermPeriod.PeriodType.HALF_TERM,
                        start_date=start_date,
                        end_date=mid_date
                    ),
                    TermPeriod(
                        school=school,
                        term=term,
                        name="Second Half",
                        period_type=TermPeriod.PeriodType.HALF_TERM,
                        start_date=mid_date + timedelta(days=1),
                        end_date=end_date
                    ),
                ])
        return term

    @transaction.atomic
    def update(self, instance, validated_data):
        school = self._get_school()
        periods_data = validated_data.pop("periods", None)

        if validated_data.get("is_active") and not instance.session.is_active:
            raise serializers.ValidationError(_("Cannot activate term under inactive session."))

        if validated_data.get("is_active") and instance.session:
            self._tenant_qs().filter(session=instance.session).exclude(pk=instance.pk).update(is_active=False)

        term_number = validated_data.get("term_number") or instance.term_number
        if not validated_data.get("term_type") and term_number:
            validated_data["term_type"] = self._determine_term_type(term_number)

        term = super().update(instance, validated_data)

        if periods_data is not None:
            term.periods.all().delete()
            periods = [TermPeriod(school=school, term=term, **p) for p in periods_data]
            TermPeriod.objects.bulk_create(periods)

        return term


# ============================================================================
# Bulk AcademicTerm Serializer
# ============================================================================
class BulkAcademicTermSerializer(serializers.Serializer):
    """
    Serializer for bulk creation of academic terms.

    Responsibilities:
    - Validates tenant scope and active session.
    - Prevents duplicate term_numbers in payload and DB.
    """

    session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.all())
    terms = serializers.ListSerializer(child=serializers.DictField())

    def _get_school(self):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        if not school:
            raise serializers.ValidationError(_("School context missing."))
        return school

    def validate(self, data):
        school = self._get_school()
        session = data["session"]

        if session.school != school:
            raise serializers.ValidationError(_("Cross-school access denied."))

        if not session.is_active:
            raise serializers.ValidationError(_("Cannot create terms under an inactive session."))

        term_numbers = [t.get("term_number") for t in data["terms"]]
        if len(term_numbers) != len(set(term_numbers)):
            raise serializers.ValidationError(_("Duplicate term_number detected in payload."))

        existing_numbers = set(
            AcademicTerm.objects.for_school(school).filter(session=session).values_list("term_number", flat=True)
        )
        if any(num in existing_numbers for num in term_numbers):
            raise serializers.ValidationError(_("One or more term_numbers already exist in this session."))

        return data
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

class AdminAssignClassroomsAndSubjectsSerializer(serializers.Serializer):
    """
    Admin-only serializer to assign classrooms and subjects to a teacher.

    Behavior:
        - Replaces teacher's classrooms and subjects with the provided lists.
        - Updates TeachingAssignments accordingly.
        - Ensures no duplicates or database constraint violations.
        - Fully transactional.
    """

    classroom_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        help_text="List of classroom UUIDs to assign to the teacher."
    )
    subject_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        help_text="List of subject UUIDs to assign to the teacher."
    )

    def validate_classroom_ids(self, ids):
        school = self.context["request"].user.school

        valid_classrooms = set(
            ClassRoom.objects.filter(id__in=ids, school=school)
            .values_list("id", flat=True)
        )

        if set(ids) != valid_classrooms:
            raise serializers.ValidationError(
                "Some classrooms do not exist or do not belong to your school."
            )

        return list(valid_classrooms)

    def validate_subject_ids(self, ids):
        school = self.context["request"].user.school

        valid_subjects = set(
            Subject.objects.filter(id__in=ids, school=school)
            .values_list("id", flat=True)
        )

        if set(ids) != valid_subjects:
            raise serializers.ValidationError(
                "Some subjects do not exist or do not belong to your school."
            )

        # Remove duplicates in input
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate subjects in input.")

        return list(valid_subjects)

    @transaction.atomic
    def save(self):
        """
        Assign classrooms and subjects to the teacher and update TeachingAssignments.

        Steps:
            1. Update teacher's classrooms and subjects M2M fields.
            2. Delete any TeachingAssignments outside the new classrooms or subjects.
            3. Create missing TeachingAssignments for every classroom + subject combination.
        """
        teacher = self.context["teacher"]
        classroom_ids = self.validated_data["classroom_ids"]
        subject_ids = self.validated_data["subject_ids"]

        # Update teacher classrooms and subjects
        teacher.classrooms.set(classroom_ids)
        teacher.subjects.set(subject_ids)
        teacher.save()

        # Remove TeachingAssignments outside the new set
        TeachingAssignment.objects.filter(teacher=teacher).exclude(
            classroom_id__in=classroom_ids,
            subject_id__in=subject_ids
        ).delete()

        # Determine all desired combinations
        desired_combinations = {
            (str(classroom_id), str(subject_id))
            for classroom_id in classroom_ids
            for subject_id in subject_ids
        }

        # Determine existing combinations
        existing_combinations = set(
            TeachingAssignment.objects.filter(teacher=teacher)
            .values_list("classroom_id", "subject_id")
        )

        # Create only missing assignments
        to_create = desired_combinations - existing_combinations
        assignments = [
            TeachingAssignment(
                teacher=teacher,
                classroom_id=classroom_id,
                subject_id=subject_id
            )
            for classroom_id, subject_id in to_create
        ]
        TeachingAssignment.objects.bulk_create(assignments)

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
