from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import serializers

from core.applications.users.api.serializers import serializers as user_serializers
from core.applications.users.api.serializers.academic_section_serializers import (
    AcademicSessionSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    AcademicTermSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    SubjectSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    TeacherDetailSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    TeacherListSerializer,
)
from core.applications.users.api.serializers.academic_section_serializers import (
    TeacherListWithAssignmentsSerializer,
)
from core.applications.users.api.serializers.admin_accessment_serializers import (
    AssessmentPolicyCreateSerializer,
)
from core.applications.users.api.serializers.admin_accessment_serializers import (
    AssessmentPolicyListSerializer,
)
from core.applications.users.api.serializers.admin_accessment_serializers import (
    AssessmentPolicyUpdateSerializer,
)
from core.applications.users.api.serializers.admin_accessment_serializers import (
    DefaultAssessmentPolicySerializer,
)
from core.applications.users.api.serializers.admin_grading_serializers import (
    DefaultGradingSystemSerializer,
)
from core.applications.users.api.serializers.admin_grading_serializers import (
    GradeScaleBulkCreateSerializer,
)
from core.applications.users.api.serializers.admin_grading_serializers import (
    GradeScaleSerializer,
)
from core.applications.users.api.serializers.admin_serializers import (
    ClassRoomCreateSerializer,
)
from core.applications.users.api.serializers.admin_serializers import (
    ClassRoomSerializer,
)
from core.helper.enums import AdmissionStatus

# Response constants
BAD_REQUEST_RESP = OpenApiResponse(
    description="Validation error. Response contains field errors.",
)
NOT_FOUND_RESP = OpenApiResponse(description="Resource not found.")
UNAUTHORIZED_RESP = OpenApiResponse(
    description="Authentication credentials were not provided or are invalid."
)

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
    return {
        "parameters": [
            TYPE_PARAM,
            SEARCH_PARAM,
            STATUS_PARAM,
            CURRENT_CLASS_PARAM,
            DEPARTMENT_PARAM,
            ORDER_PARAM,
        ],
        "summary": "List User Profiles",
        "description": (
            "Returns a paginated list of user profiles belonging to the authenticated "
            "admin’s school.\n\n"

            "REQUIRED QUERY PARAM:\n"
            "  • ?type=student | teacher | admin\n\n"

            "FILTERS (optional):\n"
            "  • ?search=<name or email> — case-insensitive\n"
            "  • ?status=PENDING | APPROVED | REJECTED\n"
            "  • ?current_class=<class> — students only\n"
            "  • ?department=<text> — teachers only\n"
            "  • ?ordering=<field> or -<field>\n\n"

            "RESPONSE STRUCTURE:\n"
            "  • type=student → StudentProfileListSerializer\n"
            "  • type=teacher → TeacherProfileListSerializer\n"
            "  • type=admin   → AdminProfileListSerializer\n\n"

            "NOTES:\n"
            "  • Results are scoped to the admin’s school (multi-tenant safe).\n"
            "  • Invalid filters return 400.\n\n"

            "EXAMPLES:\n"
            "  GET /api/admin/users/?type=student\n"
            "  GET /api/admin/users/?type=teacher&search=ada\n"
            "  GET /api/admin/users/?type=student&status=PENDING&ordering=-admission_date"
        ),
    }


def RETRIEVE_SCHEMA():
    return {
        "parameters": [TYPE_PARAM],
        "summary": "Retrieve a User Profile",
        "description": (
            "Retrieve a single user profile by ID.\n\n"

            "REQUIRED QUERY PARAM:\n"
            "  • ?type=student | teacher | admin\n\n"

            "RESPONSE STRUCTURE:\n"
            "  • Matches the serializer used in list views for the selected type.\n\n"

            "NOTES:\n"
            "  • Profile must belong to the admin’s school.\n"
            "  • Cross-school access returns 404.\n\n"

            "EXAMPLES:\n"
            "  GET /api/admin/users/12/?type=student\n"
            "  GET /api/admin/users/7/?type=teacher"
        ),
    }



def ACTIVATE_SCHEMA():
    return {
        "parameters": [TYPE_PARAM],
        "summary": "Approve or Reject a User Profile",
        "description": (
            "Approve or reject a user profile within the admin’s school.\n\n"

            "REQUIRED QUERY PARAM:\n"
            "  • ?type=student | teacher | admin\n\n"

            "REQUEST BODY:\n"
            "{\n"
            '  \"action\": \"approve\" | \"reject\",\n'
            '  \"reason\": \"Optional explanation\"\n'
            "}\n\n"

            "BEHAVIOR:\n"
            "  • Updates profile status to APPROVED or REJECTED.\n"
            "  • Automatically sets approved_by using the acting admin.\n"
            "  • Sends a notification email (best-effort).\n"
            "  • Re-approving an already approved profile is blocked.\n\n"

            "RESPONSE:\n"
            "{\n"
            "  \"detail\": \"Profile for user@email.com has been approved successfully.\"\n"
            "}\n\n"

            "NOTES:\n"
            "  • Email failure does not rollback the operation.\n"
            "  • Action is audited via service-layer logic.\n\n"

            "EXAMPLES:\n"
            "  POST /api/admin/users/12/activate/?type=student\n"
            "  POST /api/admin/users/8/activate/?type=teacher"
        ),
    }


classroom_create_schema = extend_schema(
    summary="Create a Classroom",
    description=(
        "Creates a new classroom for the authenticated admin's school.\n\n"
        "### Example Body\n"
        "```\n"
        "{\n"
        '  "academic_class": "JSS1",\n'
        '  "arm": "A"\n'
        "}\n"
        "```\n"
        "### Notes\n"
        "- School is automatically assigned.\n"
        "- Uniqueness is enforced per school.\n"
    ),
)

classroom_update_schema = extend_schema(
    summary="Update a Classroom",
    description=(
        "Modifies an existing classroom belonging to the admin's school.\n\n"
        "### Example Body\n"
        "```\n"
        "{\n"
        '  "academic_class": "JSS2",\n'
        '  "arm": "B"\n'
        "}\n"
        "```\n"
    ),
)


# ============================================================================
# Academic Session Schema Decorator
# ============================================================================
ACADEMIC_SESSION_SCHEMA = extend_schema_view(
    list=extend_schema(
        summary="List Academic Sessions",
        description="""
        Returns academic sessions for the authenticated user's school.

        Notes:
        - Results are scoped to the user's school.
        - By default this returns all sessions; frontends may filter to `is_active=true`.
        """,
        tags=["Admin Management"],
        responses={200: AcademicSessionSerializer(many=True), 401: NOT_FOUND_RESP},
    ),

    create=extend_schema(
        summary="Create Academic Session",
        description="""
        Creates a new academic session.

        Business rules:
        - Name must follow `YYYY/YYYY` or `YYYY-YYYY`.
        - If `is_active=true`, all other sessions in the same school are automatically deactivated.

        Example request body:
        ```json
        {
          "name": "2024/2025",
          "is_active": true
        }
        ```
        """,
        tags=["Admin Management"],
        request=AcademicSessionSerializer,
        responses={
            201: AcademicSessionSerializer,
            400: BAD_REQUEST_RESP,
            401: UNAUTHORIZED_RESP,
        },
    ),

    retrieve=extend_schema(
        summary="Retrieve Academic Session",
        description="Fetch a single academic session by ID.",
        tags=["Admin Management"],
        responses={200: AcademicSessionSerializer, 404: NOT_FOUND_RESP},
    ),

    update=extend_schema(
        summary="Update Academic Session",
        description="""
        Fully update an existing academic session.

        Notes:
        - Activation rules apply on update.
        - Setting `is_active=true` will automatically deactivate other sessions.
        """,
        tags=["Admin Management"],
        request=AcademicSessionSerializer,
        responses={
            200: AcademicSessionSerializer,
            400: BAD_REQUEST_RESP,
            404: NOT_FOUND_RESP,
        },
    ),

    partial_update=extend_schema(
        summary="Partially Update Academic Session",
        tags=["Admin Management"],
        request=AcademicSessionSerializer,
        responses={200: AcademicSessionSerializer, 400: BAD_REQUEST_RESP},
    ),

    destroy=extend_schema(
        summary="Deactivate Academic Session",
        description="""
        Soft-delete an academic session.

        Notes:
        - Sets `is_active=false`
        - Record remains in the database for audit/history purposes.
        """,
        tags=["Admin Management"],
        responses={204: OpenApiResponse(description="No Content")},
    ),

    open_session=extend_schema(
        summary="Open Academic Session",
        description="""
        Opens an academic session.

        Business rules:
        - Sets `is_active=true` on the selected session.
        - Automatically closes all other sessions belonging to the same school.
        - This endpoint performs a state transition and does not accept a request body.
        """,
        tags=["Admin Management"],
        responses={
            200: OpenApiResponse(
                description="Academic session opened successfully."
            ),
            404: NOT_FOUND_RESP,
        },
    ),

    close_session=extend_schema(
        summary="Close Academic Session",
        description="""
        Closes an academic session.

        Business rules:
        - Sets `is_active=false` on the selected session.
        - Does not automatically open another session.
        - This endpoint performs a state transition and does not accept a request body.
        """,
        tags=["Admin Management"],
        responses={
            200: OpenApiResponse(
                description="Academic session closed successfully."
            ),
            400: BAD_REQUEST_RESP,
            404: NOT_FOUND_RESP,
        },
    ),
)


# ============================================================================
# Academic Term Schema Decorator
# ============================================================================
ACADEMIC_TERM_SCHEMA = extend_schema_view(
    list=extend_schema(
        summary="List Academic Terms",
        description="""
        Returns academic terms for the authenticated user's school.

        Query params:
        - `session_id` (optional): Filter terms belonging to a specific session.
        """,
        parameters=[
            OpenApiParameter("session_id", str, description="Academic Session ID")
        ],
        tags=["Admin Management"],
        responses={200: AcademicTermSerializer(many=True)},
    ),

    create=extend_schema(
        summary="Create Academic Term",
        description="""
        Creates a new academic term under a session.

        Business rules:
        - Allowed term names: "First Term", "Second Term", "Third Term".
        - Only one active term per session.
        - Cannot activate a term when the parent session is inactive.

        Example request:
        ```json
        {
          "session": "<session_uuid>",
          "name": "First Term",
          "term_type": "FULL_TERM",
          "is_active": true
        }
        ```
        """,
        tags=["Admin Management"],
        request=AcademicTermSerializer,
        responses={
            201: AcademicTermSerializer,
            400: BAD_REQUEST_RESP,
            404: NOT_FOUND_RESP,
        },
    ),

    retrieve=extend_schema(
        summary="Retrieve Academic Term",
        tags=["Admin Management"],
        responses={200: AcademicTermSerializer, 404: NOT_FOUND_RESP},
    ),

    update=extend_schema(
        summary="Update Academic Term",
        description="Updates an academic term. Activation rules are enforced by the serializer.",
        tags=["Admin Management"],
        request=AcademicTermSerializer,
        responses={200: AcademicTermSerializer, 400: BAD_REQUEST_RESP},
    ),

    partial_update=extend_schema(
        summary="Partially Update Academic Term",
        tags=["Admin Management"],
        request=AcademicTermSerializer,
        responses={200: AcademicTermSerializer, 400: BAD_REQUEST_RESP},
    ),

    destroy=extend_schema(
        summary="Deactivate Academic Term",
        description="Soft delete. Marks the term as inactive (`is_active=false`).",
        tags=["Admin Management"],
        responses={204: OpenApiResponse(description="No Content")},
    ),

    # ==========================
    # SCORE ENTRY CONTROL
    # ==========================

    open_score_entry=extend_schema(
        summary="Open Term for Score Entry",
        description="""
        Opens an academic term for score entry.

        Business rules:
        - Only one term per academic session can be open for score entry at a time.
        - The parent academic session must be active.
        - Opening a term automatically closes any other active term in the same session.

        This endpoint performs a **state transition** and does not accept a request body.
        """,
        tags=["Admin Management"],
        responses={
            200: OpenApiResponse(
                description="Term successfully opened for score entry."
            ),
            400: BAD_REQUEST_RESP,
            404: NOT_FOUND_RESP,
        },
    ),

    close_score_entry=extend_schema(
        summary="Close Term for Score Entry",
        description="""
        Closes an academic term for score entry.

        Business rules:
        - Only active terms can be closed.
        - Closing a term prevents further score submissions.

        This endpoint performs a **state transition** and does not accept a request body.
        """,
        tags=["Admin Management"],
        responses={
            200: OpenApiResponse(
                description="Term successfully closed for score entry."
            ),
            400: BAD_REQUEST_RESP,
            404: NOT_FOUND_RESP,
        },
    ),
)


# ============================================================================
# Subject Schema Decorator
# ============================================================================
SUBJECT_SCHEMA = extend_schema_view(
    list=extend_schema(
        summary="List Subjects",
        description="""
        Returns all subjects belonging to the authenticated user's school.

        Features:
        - Results are scoped to the user's school (multi-tenant safe).
        - Supports case-insensitive search by subject name using `?search=<name>`.
        - Includes curriculum attributes such as mandatory status and credit hours.
        """,
        parameters=[
            OpenApiParameter(
                name="search",
                type=str,
                description="Filter subjects by name (case-insensitive).",
                required=False,
            )
        ],
        tags=["Admin Management"],
        responses={200: SubjectSerializer(many=True)},
    ),

    create=extend_schema(
        summary="Create Subject",
        description="""
        Creates a new subject for the authenticated user's school.

        Curriculum Attributes:
        - `is_mandatory` indicates whether the subject is compulsory for students
          in the assigned classrooms.
        - `credit_hour` defines the academic weight of the subject and is used
          for GPA and weighted calculations.

        Classroom Assignment:
        - `class_rooms` accepts a list of classroom UUIDs.
        - Multiple classrooms may be linked to a subject.
        - All provided classrooms must belong to the same school as the user.

        Example Request:
        ```json
        {
          "name": "Mathematics",
          "code": "MTH101",
          "description": "Basic mathematics",
          "is_mandatory": true,
          "credit_hour": 3,
          "class_rooms": [
            "<classroom_uuid_1>",
            "<classroom_uuid_2>"
          ],
          "is_active": true
        }
        ```

        Notes:
        - The `school` field is automatically inferred from the authenticated user.
        - `credit_hour` defaults to 1 if not provided.
        - Invalid or cross-school classroom IDs will result in a validation error.
        """,
        tags=["Admin Management"],
        request=SubjectSerializer,
        responses={
            201: SubjectSerializer,
            400: BAD_REQUEST_RESP,
        },
    ),

    retrieve=extend_schema(
        summary="Retrieve Subject",
        description="""
        Retrieves a single subject by ID.

        Includes:
        - Mandatory status
        - Credit hour value
        - Assigned classrooms

        Notes:
        - Subject must belong to the authenticated user's school.
        """,
        tags=["Admin Management"],
        responses={
            200: SubjectSerializer,
            404: NOT_FOUND_RESP,
        },
    ),

    update=extend_schema(
        summary="Update Subject",
        description="""
        Fully updates a subject and its classroom associations.

        Behavior:
        - If `class_rooms` is provided, existing classroom mappings
          are replaced with the new list.
        - If omitted, classroom mappings remain unchanged.

        Curriculum Updates:
        - `is_mandatory` may be toggled.
        - `credit_hour` may be updated to reflect curriculum changes.

        Notes:
        - All provided classrooms must belong to the user's school.
        - Uniqueness of subject name and code is enforced per school.
        """,
        tags=["Admin Management"],
        request=SubjectSerializer,
        responses={
            200: SubjectSerializer,
            400: BAD_REQUEST_RESP,
        },
    ),

    partial_update=extend_schema(
        summary="Partially Update Subject",
        description="""
        Partially updates subject fields.

        Classroom Update Rules:
        - Providing `class_rooms` updates classroom mappings.
        - Providing an empty list clears all classroom associations.
        - Omitting `class_rooms` leaves existing associations untouched.

        Curriculum Fields:
        - `is_mandatory` and `credit_hour` may be updated independently.
        """,
        tags=["Admin Management"],
        request=SubjectSerializer,
        responses={
            200: SubjectSerializer,
            400: BAD_REQUEST_RESP,
        },
    ),

    destroy=extend_schema(
        summary="Deactivate Subject",
        description="""
        Soft-deletes a subject by setting `is_active` to `false`.

        Notes:
        - No data is permanently removed.
        - Deactivated subjects no longer participate in curriculum,
          grading, or GPA calculations.
        """,
        tags=["Admin Management"],
        responses={
            204: OpenApiResponse(description="No Content"),
        },
    ),
)

CLASSROOM_SCHEMA = extend_schema_view(
    list=extend_schema(
        summary="List Classrooms",
        description="""
        Returns all classrooms belonging to the authenticated admin's school.

        Access Control:
        - Only School Owners and Principals can access this endpoint.

        Scope:
        - Results are strictly scoped to the authenticated user's school
          (multi-tenant isolation).

        Returned Fields:
        - `academic_class` (raw value)
        - `class_display` (human-readable academic class)
        - `arm`
        - `track` (raw value)
        - `track_display` (human-readable track)
        - `created_at`
        - `updated_at`

        Filtering:
        - `?academic_class=<value>`
        - `?track=<SCIENCE | ARTS | COMMERCIAL>`

        Search:
        - `?search=<academic_class | arm | track>`

        Ordering:
        - `?ordering=academic_class`
        - `?ordering=track`
        - `?ordering=arm`
        - `?ordering=created`

        Default Ordering:
        - academic_class → track → arm
        """,
        tags=["Admin Management"],
        responses={200: ClassRoomSerializer(many=True)},
    ),

    retrieve=extend_schema(
        summary="Retrieve Classroom",
        description="""
        Retrieves a single classroom by ID.

        Notes:
        - The classroom must belong to the authenticated user's school.
        - Includes both raw and display values for class and track.
        """,
        tags=["Admin Management"],
        responses={200: ClassRoomSerializer},
    ),

    create=extend_schema(
        summary="Create Classroom",
        description="""
        Creates a new classroom under the authenticated user's school.

        Behavior:
        - `school` is automatically inferred from the authenticated user.
        - `academic_class`, `arm`, and `track` are required.
        - Academic track must be explicitly selected.

        Uniqueness Constraint:
        - A classroom must be unique per school by the combination:
          (`academic_class`, `arm`, `track`)

        Validation Rules:
        - Duplicate classrooms within the same school are rejected.
        - Users without an associated school cannot create classrooms.

        Accepted Academic Tracks:
        - `SCIENCE`
        - `ARTS`
        - `COMMERCIAL`

        Example Request:
        ```json
        {
          "academic_class": "SS2",
          "arm": "A",
          "track": "SCIENCE"
        }
        ```

        Example Result:
        - SS2 A (Science)
        """,
        tags=["Admin Management"],
        request=ClassRoomCreateSerializer,
        responses={
            201: ClassRoomSerializer,
            400: BAD_REQUEST_RESP,
        },
    ),

    update=extend_schema(
        summary="Update Classroom",
        description="""
        Fully updates a classroom.

        Notes:
        - The classroom must belong to the authenticated user's school.
        - All required fields must be provided.
        - Uniqueness constraints are re-validated during update.
        """,
        tags=["Admin Management"],
        request=ClassRoomCreateSerializer,
        responses={
            200: ClassRoomSerializer,
            400: BAD_REQUEST_RESP,
        },
    ),

    partial_update=extend_schema(
        summary="Partially Update Classroom",
        description="""
        Partially updates a classroom.

        Notes:
        - Only provided fields are updated.
        - School ownership and uniqueness constraints are enforced.
        - Useful for updating classroom arm or track independently.
        """,
        tags=["Admin Management"],
        request=ClassRoomCreateSerializer,
        responses={
            200: ClassRoomSerializer,
            400: BAD_REQUEST_RESP,
        },
    ),

    destroy=extend_schema(
        summary="Delete Classroom",
        description="""
        Permanently deletes a classroom.

        Warning:
        - This action is irreversible.
        - Ensure the classroom is not referenced by students, subjects,
          or academic records before deletion.
        """,
        tags=["Admin Management"],
        responses={
            204: OpenApiResponse(description="No Content"),
        },
    ),
)


TeacherViewSetSchema = extend_schema_view(
    # ============================================================
    # LIST TEACHERS
    # ============================================================
    list=extend_schema(
        tags=["Admin Management"],
        summary="List All Teachers (School Scoped)",
        description=(
            "Returns a paginated list of teachers belonging to the authenticated user's school.\n\n"
            "**Use Cases:**\n"
            " - Admin or principal viewing all teachers in their school\n"
            " - Filtering staff in a multi-tenant environment\n"
            " - Supports search (by name, email, staff ID, department), ordering, and pagination\n\n"
            "**Notes:**\n"
            " - Only teachers within the authenticated user's school are returned.\n"
        ),
        responses={200: TeacherListSerializer(many=True)},
    ),

    # ============================================================
    # RETRIEVE SINGLE TEACHER
    # ============================================================
    retrieve=extend_schema(
        tags=["Admin Management"],
        summary="Retrieve a Single Teacher Profile",
        description=(
            "Fetch detailed information about a single teacher, including:\n"
            " - Personal information (name, email)\n"
            " - Professional information (staff ID, department, qualification)\n"
            " - Assigned classrooms\n"
            " - Assigned subjects\n\n"
            "**Access Control:**\n"
            " - Only accessible within the teacher's school scope"
        ),
        responses={200: TeacherDetailSerializer},
    ),

    # ============================================================
    # LIST TEACHERS WITH ASSIGNMENTS
    # ============================================================
    list_with_assignments=extend_schema(
        tags=["Admin Management"],
        summary="List Teachers with Assigned Classrooms and Subjects",
        description=(
            "Returns all teachers in the authenticated user's school along with their teaching assignments:\n"
            " - Personal info (name, email, staff ID)\n"
            " - Classrooms assigned\n"
            " - Subjects assigned\n\n"
            "**Features:**\n"
            " - Supports pagination, filtering, and ordering\n"
            " - Useful for admin dashboards or reporting\n"
            " - Nested classroom and subject objects provide full assignment context\n"
        ),
        responses={200: TeacherListWithAssignmentsSerializer(many=True)},
    ),

    # ============================================================
    # ASSIGN CLASSROOMS AND SUBJECTS
    # ============================================================
    assign_classrooms_subjects=extend_schema(
        tags=["Admin Management"],
        summary="Assign Classrooms and Subjects to a Teacher",
        description=(
            "Admin-only endpoint to assign classrooms and subjects to a specific teacher.\n\n"
            "**Behavior:**\n"
            " - Replaces the teacher's current classrooms and subjects with the provided lists\n"
            " - Updates `TeachingAssignment` objects automatically\n"
            " - Fully transactional: changes are applied atomically\n"
            " - Handles duplicates and ensures database constraints (`unique_together`) are not violated\n\n"
            "**Request Body:**\n"
            " - `classroom_ids`: List of classroom UUIDs\n"
            " - `subject_ids`: List of subject UUIDs\n\n"
            "**Notes:**\n"
            " - Only classrooms and subjects belonging to the authenticated user's school are allowed\n"
            " - Duplicate entries in `subject_ids` or `classroom_ids` are rejected\n"
        ),
        responses={
            200: TeacherDetailSerializer,
            400: "Validation errors for invalid classrooms, subjects, or duplicates",
            403: "Forbidden if the user is not an admin/principal"
        }
    ),
)

GRADING_SCHEMA = extend_schema_view(
    list=extend_schema(
        tags=["Grade Scales"],
        summary="List all grade scales for the school",
        description=(
            "Returns all grade scales configured for the authenticated user's school.\n"
            "Results are ordered by `max_score` (descending) and then by `order`.\n"
            "Teachers can only view grade scales, while principals/school owners can manage them."
        ),
        responses={200: GradeScaleSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["Grade Scales"],
        summary="Retrieve a single grade scale",
        description="Fetch details for a specific grade scale belonging to the authenticated user's school.",
        responses={200: GradeScaleSerializer},
    ),
    create=extend_schema(
        tags=["Grade Scales"],
        summary="Create a grade scale",
        description=(
            "Create a new grading scale bound to the authenticated user's school.\n"
            "**Only principals/school owners** can perform this action."
        ),
        request=GradeScaleSerializer,
        responses={201: GradeScaleSerializer},
    ),
    update=extend_schema(
        tags=["Grade Scales"],
        summary="Update a grade scale",
        description=(
            "Fully update an existing grade scale.\n"
            "The `school` field is locked and cannot be changed."
        ),
        request=GradeScaleSerializer,
        responses={200: GradeScaleSerializer},
    ),
    partial_update=extend_schema(
        tags=["Grade Scales"],
        summary="Partially update a grade scale",
        description="Update specific fields on an existing grade scale.",
        request=GradeScaleSerializer,
        responses={200: GradeScaleSerializer},
    ),
    destroy=extend_schema(
        tags=["Grade Scales"],
        summary="Delete a grade scale",
        description=(
            "Soft delete or permanently remove a grade scale. "
            "Behavior depends on backend policy. Teachers cannot delete scales."
        ),
        responses={204: OpenApiResponse(description="Grade scale deleted")},
    ),

)


GRADE_SCALE_ACTION_SCHEMAS = {
    "bulk_create": extend_schema(
        tags=["Grade Scales"],
        summary="Bulk create grading scales (atomic)",
        description=(
            "Allows admins to upload multiple grading scales at once.\n"
            "- All existing active scales are deactivated.\n"
            "- The new scales become the active grading system.\n"
            "- This operation is atomic (all-or-nothing)."
        ),
        request=GradeScaleBulkCreateSerializer,
        responses={201: OpenApiResponse(description="Bulk-created grade scales")},
    ),
    "apply_default": extend_schema(
        tags=["Grade Scales"],
        summary="Apply a predefined grading system",
        description=(
            "Apply a default grading system (e.g., *standard*, *extended*, *nigerian*).\n"
            "This resets the current active system and loads the chosen preset."
        ),
        request=DefaultGradingSystemSerializer,
        responses={200: OpenApiResponse(description="Default grading system applied")},
    ),
    "activate": extend_schema(
        tags=["Grade Scales"],
        summary="Activate a grade scale",
        description=(
            "Marks the grade scale as active. Other scales remain unchanged.\n"
            "Used when multiple grade scales exist but only some should count."
        ),
        responses={200: OpenApiResponse(description="Grade scale activated")},
    ),
    "deactivate": extend_schema(
        tags=["Grade Scales"],
        summary="Deactivate a grade scale",
        description="Marks the grade scale as inactive. Does not delete the record.",
        responses={200: OpenApiResponse(description="Grade scale deactivated")},
    ),
    "reset": extend_schema(
        tags=["Grade Scales"],
        summary="Reset grading system",
        description=(
            "Deactivates **all** active grade scales for the school.\n"
            "This does not delete records — it is a soft reset."
        ),
        responses={204: OpenApiResponse(description="Grading system reset")},
    ),
    "reorder": extend_schema(
        tags=["Grade Scales"],
        summary="Reorder grade scales",
        description=(
            "Accepts: `{ order: [ids...] }`\n"
            "- Order controls how grades show in frontend tables.\n"
            "- Highest grade should be first.\n"
            "- IDs must belong to the current school."
        ),
        request=serializers.ListField(child=serializers.IntegerField()),
        responses={200: OpenApiResponse(description="Grades reordered successfully")},
    ),
}



AssessmentPolicySchema = extend_schema_view(
    list=extend_schema(
        summary="List assessment policies",
        description="""
Retrieve all assessment policies belonging to the authenticated user's school.

Behavior:
- Automatically filtered by the user's school.
- Returns both active and inactive policies.
- Includes nested assessment types and computed total weight.
- Supports search and ordering.

Serializer:
- Uses **AssessmentPolicyListSerializer**
""",
        responses=AssessmentPolicyListSerializer,
    ),

    retrieve=extend_schema(
        summary="Retrieve an assessment policy",
        description="""
Retrieve a single assessment policy by ID.

Behavior:
- Ensures the policy belongs to the authenticated user's school.
- Returns full policy details including:
  - Term
  - CA and Exam weights
  - Nested assessment types
  - Computed total weight

Serializer:
- Uses **AssessmentPolicyListSerializer**
""",
        responses=AssessmentPolicyListSerializer,
    ),

    create=extend_schema(
        summary="Create an assessment policy",
        description="""
Create a new assessment policy for a specific academic term.

Validation rules:
- `ca_weight + exam_weight` **must equal 100%**
- Only **one active policy per school and term** is allowed

Behavior:
- School is automatically inferred from the authenticated user.
- Assessment types are not created here (added separately or via defaults).

Serializer:
- Request: **AssessmentPolicyCreateSerializer**
- Response: **AssessmentPolicyListSerializer**

Errors:
- Returns validation errors if business rules are violated.
""",
        request=AssessmentPolicyCreateSerializer,
        responses=AssessmentPolicyListSerializer,
    ),

    update=extend_schema(
        summary="Update an assessment policy",
        description="""
Update an existing assessment policy.

Rules:
- CA + Exam weights must still equal 100%.
- Term cannot be changed.
- Only one active policy per term is allowed when activating.

Serializer:
- Request: **AssessmentPolicyUpdateSerializer**
- Response: **AssessmentPolicyListSerializer**
""",
        request=AssessmentPolicyUpdateSerializer,
        responses=AssessmentPolicyListSerializer,
    ),

    partial_update=extend_schema(
        summary="Partially update an assessment policy",
        description="""
Partially update an assessment policy.

Behavior:
- Same validation rules as full update.
- Only provided fields are updated.
- Term remains immutable.

Serializer:
- Request: **AssessmentPolicyUpdateSerializer**
- Response: **AssessmentPolicyListSerializer**
""",
        request=AssessmentPolicyUpdateSerializer,
        responses=AssessmentPolicyListSerializer,
    ),

    destroy=extend_schema(
        summary="Delete an assessment policy",
        description="""
Delete an assessment policy permanently.

Behavior:
- Ensures the policy belongs to the authenticated user's school.
- Deletes the policy and all related assessment types.
- This is a **hard delete**.

Response:
- 204 No Content on success.
""",
        responses={204: None},
    ),

    # -------------------------------------------------
    # Custom actions
    # -------------------------------------------------

    apply_default=extend_schema(
        summary="Apply a default assessment policy",
        description="""
Create and activate a default assessment policy using a predefined configuration.

Available configurations:
- **standard_60_40** → Exam 60%, Tests 40%
- **half_term** → CA 50%, Half Term Exam 50%
- **detailed** → Tests, Assignments, Exam

Behavior:
- Deactivates any existing active policy for the selected term.
- Creates the policy and its assessment types atomically.
- School is inferred from the authenticated user.

Serializer:
- Request: **DefaultAssessmentPolicySerializer**
- Response: **AssessmentPolicyListSerializer**

Errors:
- Returns validation error if the selected term does not belong to the user's school.
""",
        request=DefaultAssessmentPolicySerializer,
        responses=AssessmentPolicyListSerializer,
    ),

    active_for_term=extend_schema(
        summary="Get active assessment policy for a term",
        description="""
Retrieve the active assessment policy for a given academic term.

Query Parameters:
- `term` (optional): AcademicTerm ID

Behavior:
- If `term` is provided:
  - Returns the active policy for that term.
  - Returns 404 if no active policy exists.
- If `term` is not provided:
  - Returns all active policies for the school.

Serializer:
- Response: **AssessmentPolicyListSerializer**
""",
        responses=AssessmentPolicyListSerializer,
    ),
)

# ---------------------------------------------------------------------
# Custom Actions Documentation
# ---------------------------------------------------------------------

ApplyDefaultPolicySchema = extend_schema(
    request=DefaultAssessmentPolicySerializer,
    responses={201: OpenApiResponse(description="Created default assessment policy")},
    summary="Create default assessment policy",
    description="""
Creates a pre-configured default set of AssessmentTypes under a new AssessmentPolicy.

Request Body:
{
    "term": <term_id>,
    "config_type": "standard_60_40" | "half_term" | "detailed",
    "policy_name": "Custom name"
}

What happens internally:
1. Serializer validates configuration.
2. Any active policy for that term gets deactivated.
3. A new AssessmentPolicy is created.
4. Default AssessmentTypes for the chosen config_type are created atomically.
5. Returns the fully built policy with all types included.
"""
)

ActivePolicyForTermSchema = extend_schema(
    parameters=[
        OpenApiParameter(
            name="term",
            description="AcademicTerm ID to fetch active policy for",
            required=False,
            type=int
        ),
    ],
    responses={200: AssessmentPolicyListSerializer},
    summary="Get active policy for a term",
    description="""
Fetch the currently active AssessmentPolicy for a specific term.

Usage:
- /assessment-policies/active-for-term/?term=<term_id>

What happens:
- If a term is provided, return that term’s active policy.
- If no term is provided, return all active policies across the school.
- If no active policy exists → returns 404.
"""
)

# ---------------------------------------------------------------------
# AssessmentType Schema Documentation
# ---------------------------------------------------------------------

AssessmentTypeSchema = extend_schema_view(
    list=extend_schema(
        summary="List Assessment Types",
        description="""
Retrieve all AssessmentType objects for the current user's school.

Features:
- Supports filtering by `?policy=<policy_id>`.
- Returns only types belonging to the requesting user's school.
- Includes `policy_name` and `category_display` for readability.
"""
    ),
    retrieve=extend_schema(
        summary="Retrieve a single Assessment Type",
        description="""
Return detailed information for a single AssessmentType instance.

Includes:
- Parent policy info (`policy_name`)
- Category display (`category_display`)
"""
    ),
    create=extend_schema(
        summary="Create a new Assessment Type",
        description="""
Admins only.

Validation & behavior:
1. `policy` must belong to the request user's school.
2. `weight` must not cause the total policy weight to exceed 100%.
3. Automatically assigns `order` if not provided.
4. For default policies, creation will fail if total weight exceeds 100%.
5. The type is saved under the specified policy.
"""
    ),
    update=extend_schema(
        summary="Update an Assessment Type",
        description="""
Admins only.

Validation & behavior:
1. Type cannot be moved to a policy of another school.
2. Weight constraints are enforced:
   - Excludes current type from weight calculation.
   - Total weight for the policy cannot exceed 100%.
3. `order` can be updated manually or auto-adjusted.
"""
    ),
    destroy=extend_schema(
        summary="Delete an Assessment Type",
        description="""
Hard delete an AssessmentType.

Behavior:
- Type is removed from the database.
- Ensure that the deletion does not break any active assessment policies or calculations.
"""
    ),
)
