from typing import Optional
from django.db.models import QuerySet, Q
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError, NotFound

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from drf_spectacular.utils import extend_schema

from core.applications.users.api.serializers.admin_serializers import (
    StudentProfileListSerializer,
    TeacherProfileListSerializer,
    AdminProfileListSerializer,
    UserActivationSerializer,
)
from core.applications.users.models import StudentProfile, TeacherProfile, AdminProfile
from core.applications.users.permissions import IsPrincipalOrSchoolOwner, CanActivateUsers
from core.helper.enums import AdmissionStatus

from core.applications.users.api import schemas as user_schemas


ALLOWED_TYPES = ("student", "teacher", "admin")


class AdminUsersViewset(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """
    Unified admin directory:
      - List profiles by type: ?type=student|teacher|admin
      - Retrieve a single profile (detail) with the same ?type parameter
      - Activate/reject a profile via the detail action POST /{pk}/activate/?type=...

    Filters:
      - Global search: ?search=<term> (user.name, user.email)
      - status: ?status=pending|approved|rejected
      - student-only: ?current_class=<value>
      - teacher-only: ?department=<value>
    Ordering:
      - ?ordering=<field> (supports user__name, -admission_date, etc.)
    """

    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["user__name", "user__email"]
    ordering_fields = ["user__name", "user__email", "admission_date", "student_id", "staff_id"]

    LIST_SERIALIZERS = {
        "student": StudentProfileListSerializer,
        "teacher": TeacherProfileListSerializer,
        "admin": AdminProfileListSerializer,
    }

    PROFILE_MODELS = {
        "student": StudentProfile,
        "teacher": TeacherProfile,
        "admin": AdminProfile,
    }

    # ---------------------------
    # Helpers
    # ---------------------------
    def _get_type_param(self) -> str:
        """Return validated type query param or raise ValidationError."""
        user_type = self.request.query_params.get("type")
        if not user_type:
            raise ValidationError({"type": "This query parameter is required."})
        user_type = user_type.lower()
        if user_type not in ALLOWED_TYPES:
            raise ValidationError({"type": "Invalid type. Allowed: student, teacher, admin."})
        return user_type

    def _get_model(self, user_type: str):
        return self.PROFILE_MODELS[user_type]

    def _get_serializer_class(self, user_type: str):
        return self.LIST_SERIALIZERS[user_type]

    def get_queryset(self) -> QuerySet:
        """
        Build queryset for requested profile type, scoped to the admin's school,
        applying search, filters and role-specific filters.
        """
        user_type = self._get_type_param()
        model = self._get_model(user_type)

        admin_school = self.request.user.school
        qs = model.objects.filter(user__school=admin_school).select_related("user")

        # Common filters
        params = self.request.query_params
        search = params.get("search")
        status = params.get("status")

        if search:
            qs = qs.filter(Q(user__name__icontains=search) | Q(user__email__icontains=search))

        if status:
            if status not in {AdmissionStatus.PENDING, AdmissionStatus.APPROVED, AdmissionStatus.REJECTED}:
                raise ValidationError({"status": "Invalid status value."})
            qs = qs.filter(status=status)

        # Role-specific filters
        if user_type == "student":
            current_class = params.get("current_class")
            if current_class:
                qs = qs.filter(current_class=current_class)
        elif user_type == "teacher":
            department = params.get("department")
            if department:
                qs = qs.filter(department__icontains=department)
        elif user_type == "admin":
            admin_type = params.get("admin_type")
            if admin_type:
                qs = qs.filter(admin_type=admin_type)

        return qs

    def get_serializer_class(self):
        user_type = self._get_type_param()
        return self._get_serializer_class(user_type)

    # ---------------------------
    # Schemas and endpoints
    # ---------------------------
    @extend_schema(**user_schemas.LIST_SCHEMA.kwargs)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(**user_schemas.RETRIEVE_SCHEMA.kwargs)
    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve the profile of the given id. Use ?type= to select profile model.
        """
        # Ensure requested resource belongs to admin's school and correct type
        user_type = self._get_type_param()
        Model = self._get_model(user_type)
        pk = kwargs.get("pk")

        try:
            instance = Model.objects.select_related("user").get(id=pk, user__school=request.user.school)
        except Model.DoesNotExist:
            raise NotFound(detail="Resource not found in your school.")

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @extend_schema(request=UserActivationSerializer, **user_schemas.ACTIVATE_SCHEMA.kwargs)
    @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated, CanActivateUsers], url_path="activate")
    def activate(self, request, pk=None):
        """
        Activate or reject the requested profile (detail action). Requires ?type=<role>.
        """
        # Combine pk and type into activation serializer payload for unified handling
        data = request.data.copy()
        data["id"] = pk
        # Ensure 'type' param is present when calling activation; accept query param or body
        if "type" not in data:
            data["type"] = request.query_params.get("type")

        serializer = UserActivationSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        # Optional: call email service here to notify user of status change
        # send_activation_email(instance.user)

        return Response({"detail": f"{instance.user.email} has been {instance.status}."}, status=status.HTTP_200_OK)
