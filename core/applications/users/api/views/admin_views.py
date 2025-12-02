from django.db.models import Q
from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.applications.academics.models import ClassRoom
from core.applications.users.api import schemas as user_schemas
from core.applications.users.api.schemas import classroom_create_schema
from core.applications.users.api.schemas import classroom_update_schema
from core.applications.users.api.serializers.admin_serializers import (
    AdminProfileListSerializer,
    ClassRoomCreateSerializer,
    ClassRoomSerializer,
)
from core.applications.users.api.serializers.admin_serializers import (
    StudentProfileListSerializer,
)
from core.applications.users.api.serializers.admin_serializers import (
    TeacherProfileListSerializer,
)
from core.applications.users.api.serializers.admin_serializers import (
    UserActivationSerializer,
)
from core.applications.users.models import AdminProfile
from core.applications.users.models import StudentProfile
from core.applications.users.models import TeacherProfile
from core.applications.users.permissions import CanActivateUsers
from core.applications.users.permissions import IsPrincipalOrSchoolOwner
from core.helper.enums import AdmissionStatus

ALLOWED_TYPES = ("student", "teacher", "admin")


@extend_schema(tags=["Admin User"])
@extend_schema_view(
    list=extend_schema(**user_schemas.LIST_SCHEMA()),
    retrieve=extend_schema(**user_schemas.RETRIEVE_SCHEMA()),
    activate=extend_schema(
        request=UserActivationSerializer,
        **user_schemas.ACTIVATE_SCHEMA(),
    ),
)
class AdminUsersViewset(ModelViewSet):
    """
    Central admin directory & profile management.

    Supports:
      - Listing profiles
      - Retrieving a profile
      - Activating/rejecting a profile

    Query Features:
      - ?search=<name or email>
      - ?status=<PENDING|APPROVED|REJECTED>
      - Students: ?current_class=
      - Teachers: ?department=
      - Admins: ?admin_type=
      - Ordering: ?ordering=user__name or -admission_date
    """

    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["user__name", "user__email"]
    ordering_fields = [
        "user__name",
        "user__email",
        "admission_date",
        "student_id",
        "staff_id",
    ]

    PROFILE_MODELS = {
        "student": StudentProfile,
        "teacher": TeacherProfile,
        "admin": AdminProfile,
    }

    LIST_SERIALIZERS = {
        "student": StudentProfileListSerializer,
        "teacher": TeacherProfileListSerializer,
        "admin": AdminProfileListSerializer,
    }

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _get_type_param(self) -> str:
        """Validate the ?type query parameter."""
        user_type = self.request.query_params.get("type")

        if not user_type:
            raise ValidationError({"type": "This query parameter is required."})

        user_type = user_type.lower()
        if user_type not in ALLOWED_TYPES:
            raise ValidationError(
                {"type": "Invalid type. Allowed: student, teacher, admin."},
            )

        return user_type

    def _get_model(self, user_type: str):
        return self.PROFILE_MODELS[user_type]

    def _get_serializer_for_type(self, user_type: str):
        return self.LIST_SERIALIZERS[user_type]

    # ---------------------------------------------------------------------
    # Queryset builder
    # ---------------------------------------------------------------------
    def get_queryset(self) -> QuerySet:
        """Build queryset per profile type and apply filters."""
        user_type = self._get_type_param()
        model = self._get_model(user_type)
        school = self.request.user.school

        qs = model.objects.filter(user__school=school).select_related("user")

        params = self.request.query_params

        # Search
        if params.get("search"):
            txt = params["search"]
            qs = qs.filter(Q(user__name__icontains=txt) | Q(user__email__icontains=txt))

        # Status filter
        if params.get("status"):
            status_val = params["status"]
            if status_val not in {
                AdmissionStatus.PENDING,
                AdmissionStatus.APPROVED,
                AdmissionStatus.REJECTED,
            }:
                raise ValidationError({"status": "Invalid status value."})
            qs = qs.filter(status=status_val)

        # User-type-specific filters
        if user_type == "student":
            if params.get("current_class"):
                qs = qs.filter(current_class=params["current_class"])

        elif user_type == "teacher":
            if params.get("department"):
                qs = qs.filter(department__icontains=params["department"])

        elif user_type == "admin":
            if params.get("admin_type"):
                qs = qs.filter(admin_type=params["admin_type"])

        return qs

    def get_serializer_class(self):
        return self._get_serializer_for_type(self._get_type_param())

    # ---------------------------------------------------------------------
    # Endpoints
    # ---------------------------------------------------------------------
    def retrieve(self, request, *args, **kwargs):
        """Retrieve a profile within the admin's school."""
        user_type = self._get_type_param()
        Model = self._get_model(user_type)

        try:
            instance = Model.objects.select_related("user").get(
                id=kwargs["pk"],
                user__school=request.user.school,
            )
        except Model.DoesNotExist:
            raise NotFound("Resource not found in your school.")

        return Response(self.get_serializer(instance).data)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, CanActivateUsers],
        url_path="activate",
    )
    def activate(self, request, pk=None):
        """Approve or reject a user profile."""
        data = request.data.copy()
        # NO LONGER setting data["id"] = pk
        data.setdefault("type", request.query_params.get("type"))

        serializer = UserActivationSerializer(
            data=data,
            context={
                "request": request,
                "profile_id": pk  # Pass profile_id in context
            },
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        # Enhanced response message
        action = data.get("action")
        if action == "approve":
            message = f"{instance.user.email} has been approved and notified via email."
        else:
            message = f"{instance.user.email} has been rejected and notified via email."

        return Response(
            {"detail": message},
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["Admin User"])
class ClassRoomViewSet(ModelViewSet):
    """
    CRUD for ClassRooms (JSS1 A, SS2 B, etc.)
    Only School Owners and Principals can manage classrooms.
    """

    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    filterset_fields = ["academic_class"]
    search_fields = ["arm", "academic_class"]
    ordering_fields = ["academic_class", "arm", "created"]
    ordering = ["academic_class", "arm"]

    def get_queryset(self):
        """
        Restrict classrooms to the authenticated admin's school (multi-tenant isolation).
        """
        user = self.request.user

        if not hasattr(user, "school") or user.school is None:
            return ClassRoom.objects.none()

        return ClassRoom.objects.filter(school=user.school)

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return ClassRoomCreateSerializer
        return ClassRoomSerializer

    # @classroom_create_schema
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    # @classroom_update_schema
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
