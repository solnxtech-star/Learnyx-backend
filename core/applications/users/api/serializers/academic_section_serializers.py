from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.applications.academics.models import AcademicSession
from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import Subject
from core.applications.academics.models import TeachingAssignment
from core.applications.users.models import TeacherProfile

# ============================================================================
# Academic Session Serializer
# ============================================================================


class AcademicSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for the AcademicSession model.

    Enforces PRD Rules:
    - Only one active session per school.
    - Activating a session automatically deactivates others.
    - Session names must follow YYYY/YYYY or YYYY-YYYY.
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
            "is_active",
            "term_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "school"]

    def get_term_count(self, obj):
        return obj.terms.count()

    def validate_name(self, value):
        import re

        pattern = r"^\d{4}[/-]\d{4}$"
        if not re.match(pattern, value):
            raise serializers.ValidationError(
                _("Session must follow YYYY/YYYY or YYYY-YYYY"),
            )
        return value

    def _get_school(self):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "school"):
            raise serializers.ValidationError(_("School context missing."))
        return request.user.school

    def create(self, validated_data):
        validated_data["school"] = self._get_school()

        # If set active, deactivate others
        if validated_data.get("is_active"):
            AcademicSession.objects.filter(
                school=validated_data["school"],
            ).update(is_active=False)

        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        if validated_data.get("is_active"):
            AcademicSession.objects.filter(
                school=instance.school,
            ).exclude(id=instance.id).update(is_active=False)

        return super().update(instance, validated_data)


# ============================================================================
# Academic Term Serializer
# ============================================================================


class AcademicTermSerializer(serializers.ModelSerializer):
    """
    Handles Academic Terms.

    Enforced Rules:
    - Only First, Second, Third Terms allowed
    - Only one active term per session
    - Cannot activate term under inactive session
    """

    session_name = serializers.CharField(source="session.name", read_only=True)
    is_current = serializers.SerializerMethodField()

    STANDARD_TERMS = ["First Term", "Second Term", "Third Term"]

    class Meta:
        model = AcademicTerm
        fields = [
            "id",
            "session",
            "session_name",
            "name",
            "term_type",
            "is_active",
            "is_current",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_is_current(self, obj):
        return obj.is_active and obj.session.is_active

    def _get_school(self):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "school"):
            raise serializers.ValidationError(_("School context missing."))
        return request.user.school

    def validate(self, data):
        session = data.get("session") or getattr(self.instance, "session", None)
        name = data.get("name")

        if session and session.school != self._get_school():
            raise serializers.ValidationError(_("Cross-school access denied."))

        # Enforce standard term names
        if name and name not in self.STANDARD_TERMS:
            raise serializers.ValidationError(
                _(f"Allowed terms are: {', '.join(self.STANDARD_TERMS)}"),
            )

        # Prevent duplicates
        if session and name:
            qs = AcademicTerm.objects.filter(session=session, name=name)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError(
                    _(f"'{name}' already exists in this session."),
                )

        return data

    def create(self, validated_data):
        if validated_data.get("is_active"):
            session = validated_data["session"]
            if not session.is_active:
                raise serializers.ValidationError(
                    _("Cannot activate term under inactive session."),
                )

            AcademicTerm.objects.filter(session=session).update(is_active=False)

        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        if validated_data.get("is_active"):
            if not instance.session.is_active:
                raise serializers.ValidationError(
                    _("Cannot activate term under inactive session."),
                )

            AcademicTerm.objects.filter(
                session=instance.session,
            ).exclude(id=instance.id).update(is_active=False)

        return super().update(instance, validated_data)


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
    Handles Subject management safely in multi-tenant systems.
    """

    school_name = serializers.CharField(source="school.name", read_only=True)

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
            "class_rooms",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "school"]

    def _get_school(self):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "school"):
            raise serializers.ValidationError(_("School context missing."))
        return request.user.school

    def validate_class_rooms(self, value):
        school = self._get_school()
        for classroom in value:
            if classroom.school != school:
                raise serializers.ValidationError(
                    _(f"'{classroom.name}' does not belong to your school."),
                )
        return value

    def create(self, validated_data):
        class_rooms = validated_data.pop("class_rooms", [])
        validated_data["school"] = self._get_school()

        subject = super().create(validated_data)
        subject.class_rooms.set(class_rooms)
        return subject

    def update(self, instance, validated_data):
        class_rooms = validated_data.pop("class_rooms", None)

        subject = super().update(instance, validated_data)

        if class_rooms is not None:
            subject.class_rooms.set(class_rooms)

        return subject


# ============================================================================


class TeacherListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer used for listing teacher profiles.

    Purpose:
        - Returns a summarized teacher record.
        - Used in admin/management teacher listing page.

    Returned By Endpoint:
        GET /teachers/

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

    Purpose:
        - Exposes public teacher information.
        - Includes assigned classrooms in a safe JSON format.

    Returned By Endpoint:
        GET /teachers/<id>/

    Notes:
        This serializer avoids returning raw Django model instances
        to prevent JSON serialization errors.
    """

    email = serializers.EmailField(source="user.email", read_only=True)
    classrooms = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TeacherProfile
        fields = [
            "id",
            "email",
            "qualification",
            "specialization",
            "department",
            "staff_id",
            "classrooms",
        ]

    def get_classrooms(self, obj):
        """
        Return a structured list of assigned classrooms.

        Response example:
            [
                {
                    "id": "uuid",
                    "name": "JSS1A",
                    "level": "JSS1",
                    "arm": "A",
                    "school": {
                        "id": "uuid",
                        "name": "Greenfield Academy"
                    }
                }
            ]
        """

        return [
            {
                "id": str(c.id),
                "name": f"{c.academic_class}{c.arm}",
                "level": c.academic_class,
                "arm": c.arm,
                "school": {
                    "id": str(c.school.id),
                    "name": c.school.name,
                },
            }
            for c in obj.classrooms.all()
        ]


class AdminAssignClassroomsSerializer(serializers.Serializer):
    """
    Serializer for admin-only endpoint:
    Assign multiple classrooms to a teacher.

    Purpose:
        - Admin can replace all existing classroom assignments at once.
        - Only classrooms belonging to the admin's school are allowed.

    Expected Input:
        {
            "classroom_ids": ["uuid1", "uuid2"]
        }
    """

    classroom_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        help_text="List of classroom UUIDs to assign to the teacher.",
    )

    def validate_classroom_ids(self, ids):
        """
        Validate that all classroom IDs exist and belong to the admin's school.
        """
        request = self.context["request"]
        school = request.user.school

        classrooms = ClassRoom.objects.filter(id__in=ids, school=school)

        if classrooms.count() != len(ids):
            raise serializers.ValidationError(
                "Some classrooms do not exist or do not belong to your school.",
            )

        return ids

    def save(self, teacher_profile):
        """
        Assign validated classrooms to the teacher.

        Behavior:
            - Replaces existing classroom assignments.
        """
        ids = self.validated_data["classroom_ids"]
        teacher_profile.classrooms.set(ids)
        teacher_profile.save()
        return teacher_profile


class TeacherCreateTeachingAssignmentsSerializer(serializers.Serializer):
    """
    Allows a teacher to assign themselves to teach subjects
    in different classrooms.

    Supports:
        - Bulk assignment creation
        - Duplicate prevention (via get_or_create)

    Expected Input:
        {
            "assignments": [
                {"classroom": UUID, "subject": UUID},
                ...
            ]
        }
    """

    assignments = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        help_text="List of classroom+subject assignment objects.",
    )

    def validate_assignments(self, items):
        """
        Validate that:
            - Each item has classroom + subject
            - Both belong to teacher's school
        """
        teacher = self.context["teacher"]
        school = teacher.user.school

        for item in items:
            classroom_id = item.get("classroom")
            subject_id = item.get("subject")

            if not classroom_id or not subject_id:
                raise serializers.ValidationError(
                    "Each assignment requires 'classroom' and 'subject'.",
                )

            if not ClassRoom.objects.filter(id=classroom_id, school=school).exists():
                raise serializers.ValidationError(
                    f"Invalid classroom {classroom_id} for this teacher.",
                )

            if not Subject.objects.filter(id=subject_id, school=school).exists():
                raise serializers.ValidationError(
                    f"Invalid subject {subject_id} for this teacher.",
                )

        return items

    def save(self):
        """
        Create teaching assignments.
        Uses get_or_create to avoid duplicates.
        """
        teacher = self.context["teacher"]
        created_assignments = []

        for item in self.validated_data["assignments"]:
            assignment, _ = TeachingAssignment.objects.get_or_create(
                teacher=teacher,
                classroom_id=item["classroom"],
                subject_id=item["subject"],
            )
            created_assignments.append(assignment)

        return created_assignments


class TeacherReassignTeachingAssignmentSerializer(serializers.Serializer):
    """
    Serializer for updating an existing teaching assignment.

    Editable Fields:
        - classroom (optional)
        - subject (optional)

    Validates:
        - New classroom/subject belong to teacher's school
        - No duplicate combination exists
    """

    classroom = serializers.UUIDField(required=False)
    subject = serializers.UUIDField(required=False)

    def validate(self, attrs):
        """
        Validate updated classroom/subject:
            - Must belong to school
            - Cannot duplicate an existing assignment
        """
        teacher = self.context["teacher"]
        assignment = self.context["assignment"]
        school = teacher.user.school

        new_classroom = attrs.get("classroom", assignment.classroom_id)
        new_subject = attrs.get("subject", assignment.subject_id)

        # Validate ownership
        if not ClassRoom.objects.filter(id=new_classroom, school=school).exists():
            raise serializers.ValidationError("Invalid classroom.")

        if not Subject.objects.filter(id=new_subject, school=school).exists():
            raise serializers.ValidationError("Invalid subject.")

        # Duplicate prevention
        if (
            TeachingAssignment.objects.filter(
                teacher=teacher,
                classroom_id=new_classroom,
                subject_id=new_subject,
            )
            .exclude(id=assignment.id)
            .exists()
        ):
            raise serializers.ValidationError(
                "Another assignment with this classroom+subject already exists.",
            )

        attrs["new_classroom"] = new_classroom
        attrs["new_subject"] = new_subject
        return attrs

    def save(self):
        """
        Apply reassignment update to the TeachingAssignment instance.
        """
        assignment = self.context["assignment"]
        assignment.classroom_id = self.validated_data["new_classroom"]
        assignment.subject_id = self.validated_data["new_subject"]
        assignment.save()
        return assignment


class AdminAssignSubjectsSerializer(serializers.Serializer):
    """
    Admin-only serializer for assigning subjects to teachers.

    Purpose:
        - Admin can assign one or many subjects.
        - Old subject assignments are replaced entirely.

    Expected Input:
        {
            "subject_ids": ["uuid1", "uuid2"]
        }
    """

    subject_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of subject UUIDs to assign to the teacher.",
    )

    def validate_subject_ids(self, subject_ids):
        """
        Validate that all provided subject IDs exist and
        belong to the admin's school.
        """
        request = self.context["request"]
        school = request.user.school

        subjects = Subject.objects.filter(id__in=subject_ids, school=school)

        if subjects.count() != len(subject_ids):
            raise serializers.ValidationError(
                "Some subjects do not exist or do not belong to your school.",
            )
        return subject_ids

    def save(self, teacher_profile):
        """
        Apply subject assignment:
            - Replace existing subjects.
        """
        teacher_profile.subjects.set(self.validated_data["subject_ids"])
        teacher_profile.save()
        return teacher_profile
