from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated

from core.applications.grading.api.serializers.grade_student_serializer import (
    StudentDetailSerializer,
)
from core.applications.grading.api.serializers.grade_student_serializer import (
    StudentListSerializer,
)
from core.applications.users.models import StudentProfile


@extend_schema(
    tags=["Grading"],
)
class StudentProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for Students.

    Provides:
        - GET /students/        → Paginated student list
        - GET /students/{id}/   → Detailed student profile

    Security:
        - Strictly scoped to the authenticated user's school.
        - Prevents cross-tenant data leakage.

    Performance:
        - Optimized using select_related to eliminate N+1 queries.
        - Supports filtering, searching, and ordering.
    """

    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "current_class"]
    search_fields = ["user__name", "user__email", "student_id"]
    ordering_fields = ["created_at", "admission_date"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[StudentProfile]:
        """
        Returns students belonging only to the authenticated user's school.
        """

        user = self.request.user

        if not user.school:
            return StudentProfile.objects.none()

        return (
            StudentProfile.objects
            .select_related("user", "classroom")
            .filter(user__school=user.school)
        )

    def get_serializer_class(self):
        """
        Returns serializer based on action.
        """
        if self.action == "retrieve":
            return StudentDetailSerializer
        return StudentListSerializer
