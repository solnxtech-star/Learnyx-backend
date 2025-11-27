from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiTypes,
)
from core.applications.users.api.serializers import serializers as user_serializers
from core.helper.enums import AdmissionStatus
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes

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
        summary="Student Self-Registration",
        description=(
            "Public onboarding endpoint for students.\n\n"
            "This endpoint allows a student to create an account without admin access. "
            "A new `User` is created with the **student** role, followed by the automatic creation "
            "of a linked `StudentProfile`.\n\n"
            "### How it Works\n"
            "- Validates user information (email, password, names, school code, etc.)\n"
            "- Ensures password confirmation\n"
            "- Resolves school using `school_code`\n"
            "- Automatically assigns the student to a `ClassRoom` (if provided)\n"
            "- Returns the newly created user with profile data\n\n"
            "### Permissions\n"
            "- No authentication required.\n\n"
            "### Notes\n"
            "- This endpoint is part of the unified user-creation pipeline "
            "used across all Learnxy user roles.\n"
        ),
        request=user_serializers.CustomUserCreateSerializer,
        responses={
            201: user_serializers.CustomUserSerializer,
            400: OpenApiTypes.OBJECT,
        },
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
    description=(
        "REQUIRED. Select which type of profile to operate on.\n\n"
        "Allowed values:\n"
        "  • student – Manage student profiles\n"
        "  • teacher – Manage teacher profiles\n"
        "  • admin – Manage admin/staff profiles\n\n"
        "Example:\n"
        "  /api/admin/users/?type=student\n"
        "  /api/admin/users/12/?type=teacher\n"
        "  /api/admin/users/5/activate/?type=admin"
    ),
    required=True,
    type=OpenApiTypes.STR,
    enum=["student", "teacher", "admin"],
)


SEARCH_PARAM = OpenApiParameter(
    name="search",
    location=OpenApiParameter.QUERY,
    description=(
        "Search users by name or email.\n\n"
        "Examples:\n"
        "  /api/admin/users/?type=student&search=john\n"
        "  /api/admin/users/?type=teacher&search=gmail.com\n"
    ),
    required=False,
    type=OpenApiTypes.STR,
)

STATUS_PARAM = OpenApiParameter(
    name="status",
    location=OpenApiParameter.QUERY,
    description=(
        "Filter profiles by approval status.\n\n"
        "Allowed values:\n"
        f"  • {AdmissionStatus.PENDING}\n"
        f"  • {AdmissionStatus.APPROVED}\n"
        f"  • {AdmissionStatus.REJECTED}\n\n"
        "Example:\n"
        "  /api/admin/users/?type=student&status=PENDING"
    ),
    required=False,
    type=OpenApiTypes.STR,
    enum=[AdmissionStatus.PENDING, AdmissionStatus.APPROVED, AdmissionStatus.REJECTED],
)

CURRENT_CLASS_PARAM = OpenApiParameter(
    name="current_class",
    location=OpenApiParameter.QUERY,
    description=(
        "Only applies when type=student.\n"
        "Filter students by class.\n\n"
        "Examples:\n"
        "  /api/admin/users/?type=student&current_class=SS1\n"
        "  /api/admin/users/?type=student&current_class=JSS2"
    ),
    required=False,
    type=OpenApiTypes.STR,
)


DEPARTMENT_PARAM = OpenApiParameter(
    name="department",
    location=OpenApiParameter.QUERY,
    description=(
        "Only applies when type=teacher.\n"
        "Filter teachers by department name.\n\n"
        "Examples:\n"
        "  /api/admin/users/?type=teacher&department=science\n"
        "  /api/admin/users/?type=teacher&department=mathematics"
    ),
    required=False,
    type=OpenApiTypes.STR,
)


ORDER_PARAM = OpenApiParameter(
    name="ordering",
    location=OpenApiParameter.QUERY,
    description=(
        "Sort the results.\n"
        "Prefix with '-' for descending order.\n\n"
        "Common fields:\n"
        "  • user__name\n"
        "  • user__email\n"
        "  • admission_date\n"
        "  • student_id (students)\n"
        "  • staff_id (teachers)\n\n"
        "Examples:\n"
        "  /api/admin/users/?type=student&ordering=user__name\n"
        "  /api/admin/users/?type=teacher&ordering=-admission_date"
    ),
    required=False,
    type=OpenApiTypes.STR,
)


def LIST_SCHEMA():
    return dict(
        parameters=[
            TYPE_PARAM,
            SEARCH_PARAM,
            STATUS_PARAM,
            CURRENT_CLASS_PARAM,
            DEPARTMENT_PARAM,
            ORDER_PARAM,
        ],
        summary="List Profiles",
        description=(
            "List all profiles for the selected type.\n\n"
            "REQUIRED QUERY PARAM:\n"
            "  ?type=student | teacher | admin\n\n"
            "Optional filters:\n"
            "  • ?search=john\n"
            "  • ?status=PENDING\n"
            "  • ?current_class=SS1 (only for students)\n"
            "  • ?department=science (only for teachers)\n"
            "  • ?ordering=user__name\n\n"
            "Examples:\n"
            "  GET /api/admin/users/?type=student\n"
            "  GET /api/admin/users/?type=teacher&search=ada\n"
            "  GET /api/admin/users/?type=student&status=PENDING&ordering=-admission_date"
        ),
    )


def RETRIEVE_SCHEMA():
    return dict(
        parameters=[TYPE_PARAM],
        summary="Retrieve a Profile",
        description=(
            "Retrieve a single profile by ID.\n\n"
            "REQUIRED QUERY PARAM:\n"
            "  ?type=student | teacher | admin\n\n"
            "Examples:\n"
            "  GET /api/admin/users/12/?type=student\n"
            "  GET /api/admin/users/7/?type=teacher"
        ),
    )


def ACTIVATE_SCHEMA():
    return dict(
        parameters=[TYPE_PARAM],
        summary="Activate or Reject a Profile",
        description=(
            "Approve or reject a profile.\n\n"
            "REQUIRED QUERY PARAM:\n"
            "  ?type=student | teacher | admin\n\n"
            "POST BODY EXAMPLE:\n"
            "{\n"
            '  "action": "approve",  // or reject\n'
            '  "reason": "Documents verified"\n'
            "}\n\n"
            "Examples:\n"
            "  POST /api/admin/users/12/activate/?type=student\n"
            "  POST /api/admin/users/8/activate/?type=teacher"
        ),
    )

classroom_create_schema = extend_schema(
        summary="Create a Classroom",
        description=(
            "Creates a new classroom for the authenticated admin's school.\n\n"
            "### Example Body\n"
            "```\n"
            "{\n"
            "  \"academic_class\": \"JSS1\",\n"
            "  \"arm\": \"A\"\n"
            "}\n"
            "```\n"
            "### Notes\n"
            "- School is automatically assigned.\n"
            "- Uniqueness is enforced per school.\n"
        )
    )

classroom_update_schema = extend_schema(
        summary="Update a Classroom",
        description=(
            "Modifies an existing classroom belonging to the admin's school.\n\n"
            "### Example Body\n"
            "```\n"
            "{\n"
            "  \"academic_class\": \"JSS2\",\n"
            "  \"arm\": \"B\"\n"
            "}\n"
            "```\n"
        )
    )