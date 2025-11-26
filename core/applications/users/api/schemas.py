from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiTypes,
)
from core.applications.users.api.serializers import serializers as user_serializers
from core.helper.enums import AdmissionStatus


user_schema = extend_schema_view(
    # ============================================================
    # USER CRUD & SELF MANAGEMENT
    # ============================================================
    list=extend_schema(
        summary="List Users",
        description=(
            "Returns a paginated list of all users in the system.\n\n"
            "**Access Control:**\n"
            "- Only administrators can list users.\n"
            "- If `HIDE_USERS=True`, non-admins will only see their own account."
        ),
        responses={200: user_serializers.CustomUserSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve a User",
        description=(
            "Returns full details about a specific user using their ID.\n\n"
            "Includes role, profile metadata, and onboarding information."
        ),
        responses={200: user_serializers.CustomUserSerializer},
    ),
    me=extend_schema(
        summary="Current Authenticated User",
        description=(
            "Endpoint for retrieving, updating, or deleting the authenticated "
            "user's own profile.\n\n"
            "**Supported Methods:**\n"
            "- `GET`: Fetch user profile\n"
            "- `PUT`: Full update\n"
            "- `PATCH`: Partial update\n"
            "- `DELETE`: Permanently delete own account"
        ),
        responses={200: user_serializers.CustomUserSerializer},
    ),
    get_by_email=extend_schema(
        summary="Find User by Email",
        description=(
            "Search for a user using an email address and return their profile.\n\n"
            "Useful for admin dashboards, invite flows, and account lookup."
        ),
        responses={200: user_serializers.UserSerializer.Info},
    ),
    # ============================================================
    # USER REGISTRATION & ONBOARDING
    # ============================================================
    register_student=extend_schema(
        summary="Register a Student",
        description=(
            "Self-service registration endpoint for students.\n"
            "Creates a new user with the **student role** and automatically "
            "creates a `StudentProfile`.\n\n"
            "Uses the unified user creation + onboarding pipeline.\n"
            "No admin privileges needed."
        ),
        request=user_serializers.CustomUserCreateSerializer,
        responses={201: user_serializers.CustomUserSerializer},
    ),
    register_teacher=extend_schema(
        summary="Register a Teacher (Admin Only)",
        description=(
            "Create a new teacher account.\n\n"
            "**Important:**\n"
            "- Only admins or superusers can access this endpoint.\n"
            "- Automatically generates a `TeacherProfile`.\n"
            "- Supports SaaS tenant assignment (schools, institutions)."
        ),
        request=user_serializers.CustomTeacherCreateSerializer,
        responses={201: user_serializers.CustomUserSerializer},
    ),
    register_admin=extend_schema(
        summary="Register a New Admin",
        description=(
            "Create an additional admin account.\n\n"
            "**Access Control:**\n"
            "- Only existing admins or superusers may use this endpoint.\n\n"
            "Used for onboarding staff, team members, or organization owners."
        ),
        request=user_serializers.CustomAdminCreateSerializer,
        responses={201: user_serializers.CustomUserSerializer},
    ),
    # ============================================================
    # ACCOUNT ACTIVATION & EMAIL VERIFICATION
    # ============================================================
    activation=extend_schema(
        summary="Activate Account",
        description=(
            "Verify and activate a newly created user account.\n\n"
            "Typically used after clicking an activation link sent to email.\n"
            "Follows Djoser-style token activation."
        ),
        request=user_serializers.ActivationSerializer,
        responses={204: None},
    ),
    resend_activation=extend_schema(
        summary="Resend Activation Link",
        description=(
            "Resends the activation email for users who have registered "
            "but have not activated their account.\n\n"
            "Useful when a user does not receive the initial email."
        ),
        responses={204: None},
    ),
    # ============================================================
    # PASSWORD RESET & UPDATE FLOW
    # ============================================================
    reset_password=extend_schema(
        summary="Request Password Reset",
        description=(
            "Sends a password reset email to the provided email address.\n\n"
            "If the email exists, a reset token is generated and sent.\n"
            "No information is leaked about whether the user exists."
        ),
        responses={204: None},
    ),
    reset_password_confirm=extend_schema(
        summary="Reset Password (Confirm)",
        description=(
            "Complete the password reset process using the reset token.\n"
            "Sets the user's new password and optionally sends a confirmation email."
        ),
        request=user_serializers.PasswordResetConfirmSerializer,
        responses={204: None},
    ),
    set_password=extend_schema(
        summary="Change Password (Authenticated User)",
        description=(
            "Allows logged-in users to change their password.\n\n"
            "Supports optional session refresh and email confirmation."
        ),
        request=user_serializers.PasswordSerializer,
        responses={204: None},
    ),
    # ============================================================
    # DEVICES (OPTIONAL MODULE)
    # ============================================================
    list_devices=extend_schema(
        summary="List User Devices",
        description=(
            "Returns all devices linked to the authenticated user's account.\n"
            "Useful for session management, push notifications, and device audits."
        ),
    ),
)


TYPE_PARAM = OpenApiParameter(
    name="type",
    location=OpenApiParameter.QUERY,
    description="Profile type to operate on. Allowed values: student, teacher, admin.",
    required=True,
    type=OpenApiTypes.STR,
    enum=["student", "teacher", "admin"],
)

SEARCH_PARAM = OpenApiParameter(
    name="search",
    location=OpenApiParameter.QUERY,
    description="Search across user name and email.",
    required=False,
    type=OpenApiTypes.STR,
)

STATUS_PARAM = OpenApiParameter(
    name="status",
    location=OpenApiParameter.QUERY,
    description="Filter by profile status.",
    required=False,
    type=OpenApiTypes.STR,
    enum=[AdmissionStatus.PENDING, AdmissionStatus.APPROVED, AdmissionStatus.REJECTED],
)

CURRENT_CLASS_PARAM = OpenApiParameter(
    name="current_class",
    location=OpenApiParameter.QUERY,
    description="Filter students by current_class.",
    required=False,
    type=OpenApiTypes.STR,
)

DEPARTMENT_PARAM = OpenApiParameter(
    name="department",
    location=OpenApiParameter.QUERY,
    description="Filter teachers by department.",
    required=False,
    type=OpenApiTypes.STR,
)

ORDER_PARAM = OpenApiParameter(
    name="ordering",
    location=OpenApiParameter.QUERY,
    description="Ordering fields, e.g. 'user__name' or '-admission_date'.",
    required=False,
    type=OpenApiTypes.STR,
)

LIST_SCHEMA = extend_schema(
    parameters=[
        TYPE_PARAM,
        SEARCH_PARAM,
        STATUS_PARAM,
        CURRENT_CLASS_PARAM,
        DEPARTMENT_PARAM,
        ORDER_PARAM,
    ],
    description="List profiles in the administrator's school. Use ?type=student|teacher|admin. Supports search, filters and ordering.",
)

RETRIEVE_SCHEMA = extend_schema(
    parameters=[TYPE_PARAM],
    description="Retrieve a single profile resource by id. Supply ?type=student|teacher|admin",
)

ACTIVATE_SCHEMA = extend_schema(
    request=None,  # override in view if you want to display serializer
    parameters=[TYPE_PARAM],
    description="Activate (approve) or reject a profile. Only School Owner or Principal can call this.",
)
