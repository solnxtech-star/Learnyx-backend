from django.db import transaction
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from core.applications.academics.api.schemas import STUDENT_VIEWSET_SCHEMA
from core.applications.academics.api.schemas import AssessmentEntryFormDataSchema
from core.applications.academics.api.schemas import AssessmentRecordSchema
from core.applications.academics.api.schemas import BulkAssessmentEntrySchema
from core.applications.academics.api.serializers.accessment_entry_serializers import (
    AdminAssignSubjectsToStudentSerializer,
)
from core.applications.academics.api.serializers.accessment_entry_serializers import (
    AssessmentEntryFormDataSerializer,
)
from core.applications.academics.api.serializers.accessment_entry_serializers import (
    AssessmentRecordSerializer,
)
from core.applications.academics.api.serializers.accessment_entry_serializers import (
    BulkAssessmentEntrySerializer,
)
from core.applications.academics.api.serializers.accessment_entry_serializers import (
    StudentCurrentClassSerializer,
)
from core.applications.academics.api.serializers.accessment_entry_serializers import (
    StudentDetailSerializer,
)
from core.applications.academics.api.serializers.accessment_entry_serializers import (
    StudentListSerializer,
)
from core.applications.academics.api.serializers.accessment_entry_serializers import (
    StudentPromotionSerializer,
)
from core.applications.academics.api.serializers.accessment_entry_serializers import (
    StudentUpdateSerializer,
)
from core.applications.academics.models import AssessmentRecord
from core.applications.academics.models import AssessmentType
from core.applications.academics.models import StudentSubjectEnrollment
from core.applications.users.models import StudentProfile
from core.helper.permissions import IsPrincipalOrSchoolOwner
from core.helper.permissions import IsPrincipalOwnerOrAssignedTeacher


@STUDENT_VIEWSET_SCHEMA
class StudentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Student Read-Only API.

    Provides:
        - List students with current classroom
        - Retrieve student with enrollment history
        - Update student profile (admin only)
        - Admin-only subject assignment per session & term
    """

    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    queryset = (
        StudentProfile.objects
        .select_related("user", "classroom")
        .prefetch_related(
            "enrollments__classroom",
            "enrollments__session",
            "enrollments__term",
        )
    )

    # ---------------------------------------------------------
    # Serializer routing
    # ---------------------------------------------------------
    def get_serializer_class(self):
        if self.action == "list":
            return StudentListSerializer
        if self.action == "retrieve":
            return StudentDetailSerializer
        if self.action == "update_profile":
            return StudentUpdateSerializer
        return StudentDetailSerializer

    # ---------------------------------------------------------
    # Multi-tenancy scoping
    # ---------------------------------------------------------
    def get_queryset(self):
        school = self.request.user.school
        return super().get_queryset().filter(user__school=school)

    # =========================================================
    # UPDATE → Edit Student Profile
    # =========================================================
    @action(
        methods=["PATCH"],
        detail=True,
        url_path="update-profile",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def update_profile(self, request, pk=None):
        """
        Update student + nested user information.
        """

        student = self.get_object()

        serializer = StudentUpdateSerializer(
            student,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "message": "Student profile updated successfully",
                "student_id": student.id,
            }
        )

    # =========================================================
    # LIST → Current Classes
    # =========================================================
    @action(
        methods=["GET"],
        detail=False,
        url_path="current-classes",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def current_classes(self, request):
        """
        List students with their current academic class and classroom.
        """
        queryset = self.get_queryset()

        serializer = StudentCurrentClassSerializer(
            queryset,
            many=True,
        )
        return Response(serializer.data)

    # =========================================================
    # ADMIN → Assign Subjects
    # =========================================================
    @action(
        methods=["POST"],
        detail=True,
        url_path="assign-subjects",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def assign_subjects(self, request, pk=None):
        """
        Assign subjects to a student for a given session and term.

        This replaces all existing assignments for that session & term.
        """
        student = self.get_object()

        serializer = AdminAssignSubjectsToStudentSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        enrollments = serializer.save(student=student)

        return Response(
            {
                "message": "Subjects assigned successfully",
                "student_id": student.id,
                "count": len(enrollments),
            },
        )

    @action(
        methods=["POST"],
        detail=False,  # operates on multiple students at once
        url_path="promote-students",
        permission_classes=[IsAuthenticated, IsPrincipalOrSchoolOwner],
    )
    def promote_students(self, request):
        """
        Promote or demote multiple students to a target class and academic session.

        Request example:
        {
            "student_ids": [1, 2, 3],
            "target_class_id": 5,
            "academic_session_id": 2,
            "reason": "End-of-year promotion"
        }

        Response example:
        {
            "message": "Students promoted successfully",
            "promoted_count": 3,
            "assignments": [
                {"student_id": 1, "classroom": "Grade 3A", "session": "2025/2026"},
                ...
            ]
        }
        """
        serializer = StudentPromotionSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        # Save all promotions in a single atomic transaction
        assignments = serializer.save()

        # Build response
        response_data = [
            {
                "student_id": a.student_id,
                "classroom": a.classroom.arm,
                "session": a.academic_session.name,
            }
            for a in assignments
        ]

        return Response(
            {
                "message": "Students promoted successfully",
                "promoted_count": len(assignments),
                "assignments": response_data,
            },
            status=status.HTTP_200_OK,
        )

# ----------------------------------------
# CRUD for individual assessment records
# ----------------------------------------
@AssessmentRecordSchema
class AssessmentRecordViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for individual assessment records.
    """
    serializer_class = AssessmentRecordSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOwnerOrAssignedTeacher]

    def get_queryset(self):
        """
        Restrict queryset to assessment records belonging to the user's school.
        Includes select_related for efficiency.
        """
        school = self.request.user.school
        return AssessmentRecord.objects.filter(
            student__school=school
        ).select_related(
            "student__user",
            "classroom_subject__subject",
            "assessment_type"
        )

    def perform_create(self, serializer):
        # Automatically calculates percentage_score in serializer
        return serializer.save()

    def perform_update(self, serializer):
        return serializer.save()


# ----------------------------------------
# Loads data for assessment entry forms
# ----------------------------------------
@AssessmentEntryFormDataSchema
class AssessmentEntryViewSet(ViewSet):
    """
    Provides all data needed for teachers to enter assessments.
    """
    permission_classes = [IsAuthenticated, IsPrincipalOwnerOrAssignedTeacher]

    def create(self, request, *args, **kwargs):
        serializer = AssessmentEntryFormDataSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        class_room = serializer.validated_data["class_room"]
        subject = serializer.validated_data["subject"]
        school = request.user.school

        # Fetch only students enrolled in the subject via StudentSubjectEnrollment
        enrolled_student_ids = StudentSubjectEnrollment.objects.filter(
            subject=subject,
            session=class_room.current_session,
            term=class_room.current_term,
            student__is_active=True,
            student__school=school
        ).select_related("student__user").values_list("student_id", flat=True)

        students = StudentProfile.objects.filter(id__in=enrolled_student_ids).select_related("user")

        assessment_types = AssessmentType.objects.filter(
            policy__school=school
        )

        return Response({
            "class_room": {"id": class_room.id, "name": class_room.name},
            "subject": {"id": subject.id, "name": subject.name},
            "students": [
                {
                    "id": s.id,
                    "name": s.user.name,
                    "student_id": s.student_id,
                }
                for s in students
            ],
            "assessment_types": [
                {
                    "id": a.id,
                    "name": a.name,
                    "count": a.max_assessments,
                    "max_score": a.max_score,
                }
                for a in assessment_types
            ],
        })


# ----------------------------------------
# Bulk creation/update of assessment records
# ----------------------------------------
@BulkAssessmentEntrySchema
class BulkAssessmentEntryViewSet(ViewSet):
    """
    Handles bulk creation and updating of assessment records.
    """
    permission_classes = [IsAuthenticated, IsPrincipalOwnerOrAssignedTeacher]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Validates and processes multiple student scores in one request.
        Uses serializers for all validations and percentage score calculations.
        """
        serializer = BulkAssessmentEntrySerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        result = serializer.save()
        return Response(result, status=status.HTTP_200_OK)
