from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view, OpenApiExample

from rest_framework import serializers
from core.applications.users.api.serializers import serializers as user_serializers
from core.applications.users.api.serializers.academic_section_serializers import (
    AcademicSessionSerializer,
    AcademicTermSerializer,
    AdminAssignClassroomsSerializer,
    AdminAssignSubjectsSerializer,
    SubjectSerializer,
    TeacherCreateTeachingAssignmentsSerializer,
    TeacherDetailSerializer,
    TeacherListSerializer,
    TeacherReassignTeachingAssignmentSerializer,
)
from core.applications.users.api.serializers.admin_grading_serializers import (
    DefaultGradingSystemSerializer,
    GradeScaleBulkCreateSerializer,
    GradeScaleSerializer,
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
        tags=["Academics"],
        responses={200: AcademicSessionSerializer(many=True), 401: NOT_FOUND_RESP},
    ),
    create=extend_schema(
        summary="Create Academic Session",
        description="""
        Creates a new academic session.

        Business rules:
        - Name must follow `YYYY/YYYY` or `YYYY-YYYY`.
        - If `is_active=true`, all other sessions in the same school are automatically deactivated.

        Validation notes:
        - Serializer will return 400 when name format is invalid or school context is missing.

        Example request body:
        ```json
        {
          "name": "2024/2025",
          "is_active": true
        }
        ```
        """,
        tags=["Academics"],
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
        tags=["Academics"],
        responses={200: AcademicSessionSerializer, 404: NOT_FOUND_RESP},
    ),
    update=extend_schema(
        summary="Update Academic Session",
        description="""
        Fully update an existing session.

        Notes:
        - Activation rules apply on update (activating will deactivate other sessions).
        """,
        tags=["Academics"],
        request=AcademicSessionSerializer,
        responses={
            200: AcademicSessionSerializer,
            400: BAD_REQUEST_RESP,
            404: NOT_FOUND_RESP,
        },
    ),
    partial_update=extend_schema(
        summary="Partially update Academic Session",
        tags=["Academics"],
        request=AcademicSessionSerializer,
        responses={200: AcademicSessionSerializer, 400: BAD_REQUEST_RESP},
    ),
    destroy=extend_schema(
        summary="Deactivate Academic Session",
        description="Soft-delete: sets `is_active=false`. Record remains in DB.",
        tags=["Academics"],
        responses={204: OpenApiResponse(description="No Content")},
    ),
)


# ============================================================================
# Academic Term Schema Decorator
# ============================================================================
ACADEMIC_TERM_SCHEMA = extend_schema_view(
    list=extend_schema(
        summary="List Academic Terms",
        description="""
        Returns terms for the authenticated user's school.

        Query params:
        - `session_id` (optional): filter terms belonging to a specific session.
        """,
        parameters=[
            OpenApiParameter("session_id", str, description="Academic Session ID")
        ],
        tags=["Academics"],
        responses={200: AcademicTermSerializer(many=True)},
    ),
    create=extend_schema(
        summary="Create Academic Term",
        description="""
        Creates a new term under a session.

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
        tags=["Academics"],
        request=AcademicTermSerializer,
        responses={
            201: AcademicTermSerializer,
            400: BAD_REQUEST_RESP,
            404: NOT_FOUND_RESP,
        },
    ),
    retrieve=extend_schema(
        summary="Retrieve Academic Term",
        tags=["Academics"],
        responses={200: AcademicTermSerializer, 404: NOT_FOUND_RESP},
    ),
    update=extend_schema(
        summary="Update Academic Term",
        description="Updates a term. Activation rules enforced by serializer.",
        tags=["Academics"],
        request=AcademicTermSerializer,
        responses={200: AcademicTermSerializer, 400: BAD_REQUEST_RESP},
    ),
    partial_update=extend_schema(
        summary="Partially update Academic Term",
        tags=["Academics"],
        request=AcademicTermSerializer,
        responses={200: AcademicTermSerializer, 400: BAD_REQUEST_RESP},
    ),
    destroy=extend_schema(
        summary="Deactivate Academic Term",
        description="Soft-delete by setting `is_active=false`.",
        tags=["Academics"],
        responses={204: OpenApiResponse(description="No Content")},
    ),
)


# ============================================================================
# Subject Schema Decorator
# ============================================================================
SUBJECT_SCHEMA = extend_schema_view(
    list=extend_schema(
        summary="List Subjects",
        description="""
        Returns subjects for the authenticated user's school.

        Supports search via `?search=<name>`.
        """,
        parameters=[
            OpenApiParameter("search", str, description="Search by subject name")
        ],
        tags=["Academics"],
        responses={200: SubjectSerializer(many=True)},
    ),
    create=extend_schema(
        summary="Create Subject",
        description="""
        Creates a subject. Optionally link to classrooms by their IDs.

        Request example:
        ```json
        {
          "name": "Mathematics",
          "code": "MTH101",
          "description": "Basic math",
          "class_rooms": ["<classroom_uuid_1>", "<classroom_uuid_2>"],
          "is_active": true
        }
        ```
        Validation:
        - All class_rooms must belong to the same school (validated by serializer).
        """,
        tags=["Academics"],
        request=SubjectSerializer,
        responses={201: SubjectSerializer, 400: BAD_REQUEST_RESP},
    ),
    retrieve=extend_schema(
        summary="Retrieve Subject",
        tags=["Academics"],
        responses={200: SubjectSerializer, 404: NOT_FOUND_RESP},
    ),
    update=extend_schema(
        summary="Update Subject",
        description="Updates subject and its classroom mappings.",
        tags=["Academics"],
        request=SubjectSerializer,
        responses={200: SubjectSerializer, 400: BAD_REQUEST_RESP},
    ),
    partial_update=extend_schema(
        summary="Partially update Subject",
        tags=["Academics"],
        request=SubjectSerializer,
        responses={200: SubjectSerializer, 400: BAD_REQUEST_RESP},
    ),
    destroy=extend_schema(
        summary="Deactivate Subject",
        description="Soft-delete via `is_active=false`.",
        tags=["Academics"],
        responses={204: OpenApiResponse(description="No Content")},
    ),
)

TeacherViewSetSchema = extend_schema_view(
    # ============================================================
    # LIST TEACHERS
    # ============================================================
    list=extend_schema(
        summary="List All Teachers (School Restricted)",
        description=(
            "Returns a list of teachers belonging to the authenticated user's school.\n\n"
            "Use this endpoint for:\n"
            " - Admin viewing all teachers\n"
            " - Filtering staff in a multi-tenant environment\n"
        ),
        responses={200: TeacherListSerializer},
    ),
    # ============================================================
    # RETRIEVE SINGLE TEACHER
    # ============================================================
    retrieve=extend_schema(
        summary="Retrieve a Teacher Profile",
        description=(
            "Fetch detailed information about a single teacher, including:\n"
            " - Personal + professional data\n"
            " - Assigned classrooms\n"
            " - Assigned subjects\n\n"
            "Only accessible within the school scope."
        ),
        responses={200: TeacherDetailSerializer},
    ),
    # ============================================================
    # ADMIN: ASSIGN CLASSROOMS
    # ============================================================
    assign_classrooms=extend_schema(
        summary="Assign Classrooms to Teacher (Admin Only)",
        description=(
            "**ADMIN ACTION**\n\n"
            "Assign one or multiple classrooms to a teacher.\n"
            "This action *replaces all existing classroom assignments.*\n\n"
            "Validations:\n"
            " - Classroom IDs must exist\n"
            " - All must belong to admin’s school\n"
        ),
        request=AdminAssignClassroomsSerializer,
        responses={
            200: TeacherDetailSerializer,
            400: OpenApiResponse(description="Invalid classroom IDs"),
            403: OpenApiResponse(description="Not allowed"),
        },
        examples=[
            OpenApiExample(
                "Assign Classrooms Example",
                value={"classroom_ids": ["uuid-123", "uuid-456"]},
            )
        ],
    ),
    # ============================================================
    # ADMIN: ASSIGN SUBJECTS
    # ============================================================
    assign_subjects=extend_schema(
        summary="Assign Subjects to Teacher (Admin Only)",
        description=(
            "**ADMIN ACTION**\n\n"
            "Assign one or multiple subjects to a teacher.\n"
            "This **fully replaces** previous subject assignments.\n\n"
            "Validations:\n"
            " - All subjects must exist\n"
            " - Must belong to admin’s school"
        ),
        request=AdminAssignSubjectsSerializer,
        responses={
            200: TeacherDetailSerializer,
            400: OpenApiResponse(description="Invalid subject IDs"),
            403: OpenApiResponse(description="Not allowed"),
        },
    ),
    # ============================================================
    # TEACHER: BULK CREATE TEACHING ASSIGNMENTS
    # ============================================================
    assign_teaching=extend_schema(
        summary="Teacher: Bulk Assign Classroom + Subject Combinations",
        description=(
            "**TEACHER ACTION**\n\n"
            "Allows a teacher to assign themselves to multiple classes and subjects.\n"
            "Useful for bulk creation of teaching roles.\n\n"
            "Validations:\n"
            " - Classroom + Subject must belong to teacher’s school\n"
            " - Avoids creating duplicates using `get_or_create`\n"
        ),
        request=TeacherCreateTeachingAssignmentsSerializer,
        responses={
            200: OpenApiResponse(description="Assignments Created Successfully"),
            403: OpenApiResponse(
                description="Teacher cannot assign on behalf of others"
            ),
        },
        examples=[
            OpenApiExample(
                "Bulk Teaching Assignment Example",
                value={
                    "assignments": [
                        {"classroom": "uuid-101", "subject": "uuid-201"},
                        {"classroom": "uuid-102", "subject": "uuid-202"},
                    ]
                },
            )
        ],
    ),
    # ============================================================
    # TEACHER: UPDATE SINGLE TEACHING ASSIGNMENT
    # ============================================================
    reassign_teaching=extend_schema(
        summary="Teacher: Update an Existing Teaching Assignment",
        description=(
            "**TEACHER ACTION**\n\n"
            "Allows a teacher to modify one of their teaching assignments.\n"
            "Teachers can change:\n"
            " - classroom\n"
            " - subject\n"
            " - or both\n\n"
            "Validations:\n"
            " - New classroom/subject must be valid for school\n"
            " - Duplicate combinations are prevented\n"
        ),
        request=TeacherReassignTeachingAssignmentSerializer,
        responses={
            200: OpenApiResponse(description="Assignment Updated Successfully"),
            404: OpenApiResponse(description="Assignment Not Found"),
            403: OpenApiResponse(
                description="Cannot modify another teacher's assignment"
            ),
        },
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
