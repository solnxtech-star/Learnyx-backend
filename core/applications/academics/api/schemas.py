from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view

from core.applications.academics.api.serializers.accessment_entry_serializers import (
    AdminAssignSubjectsToStudentSerializer,
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
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    AssessmentEntryCreateSerializer,
    AssessmentEntrySerializer,
    TeacherSubjectClassTermSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    AssessmentTypeSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    ClassroomStudentSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    ResultSnapshotSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentContactSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentProfileDetailSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentSubjectMatchSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentSubjectResultSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    SubjectResultSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    TeacherClassroomSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    TeacherSubjectSerializer,
)

STUDENT_VIEWSET_SCHEMA = extend_schema_view(
    list=extend_schema(
        tags=["Admin Management"],
        summary="List students",
        description=(
            "Returns a list of students belonging to the authenticated user's school.\n\n"
            "Each student includes:\n"
            "- Basic user information\n"
            "- Current classroom assignment\n\n"
            "**Permissions:** Principal / School Owner only."
        ),
        responses={200: StudentListSerializer(many=True)},
    ),

    retrieve=extend_schema(
        tags=["Admin Management"],
        summary="Retrieve student details",
        description=(
            "Retrieve detailed information about a single student.\n\n"
            "Includes:\n"
            "- Student bio data\n"
            "- Current classroom\n"
            "- Full enrollment history (session & term aware)\n\n"
            "**Permissions:** Principal / School Owner only."
        ),
        responses={
            200: StudentDetailSerializer,
            404: OpenApiResponse(description="Student not found"),
        },
    ),

    # ✅ Update Profile
    update_profile=extend_schema(
        tags=["Admin Management"],
        summary="Update student profile",
        description=(
            "Update a student's profile information including nested user data.\n\n"
            "### Editable Fields\n"
            "- user.name\n"
            "- user.email\n"
            "- user.phone_number\n"
            "- guardian_name\n"
            "- guardian_phone\n"
            "- address\n"
            "- gender\n"
            "- admission_date\n\n"
            "This endpoint supports **partial updates (PATCH)**.\n\n"
            "**Permissions:** Principal / School Owner only.\n"
            "**Multi-tenant safe:** Students must belong to the same school."
        ),
        request=StudentUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Student profile updated successfully",
                examples=[
                    OpenApiExample(
                        "Success response",
                        value={
                            "message": "Student profile updated successfully",
                            "student_id": "uuid",
                        },
                    ),
                ],
            ),
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Student not found"),
        },
    ),

    # ✅ Current Classes
    current_classes=extend_schema(
        tags=["Admin Management"],
        summary="List students with current class",
        description=(
            "Returns all students in the authenticated user's school along with their "
            "current academic class and classroom.\n\n"
            "This endpoint is optimized for dashboards, dropdowns, promotion screens, "
            "and subject assignment workflows.\n\n"
            "**Permissions:** Principal / School Owner only."
        ),
        responses={200: StudentCurrentClassSerializer(many=True)},
    ),

    # ✅ Assign Subjects
    assign_subjects=extend_schema(
        tags=["Admin Management"],
        summary="Assign subjects to a student",
        description=(
            "Assign subjects to a student for a specific academic session and term.\n\n"
            "### Important behavior\n"
            "- This operation **REPLACES** all existing subject assignments "
            "for the selected session and term.\n"
            "- Subjects must belong to the same school as the admin.\n"
            "- Assignments are tracked with `assigned_by` for auditing.\n\n"
            "**Permissions:** Principal / School Owner only."
        ),
        request=AdminAssignSubjectsToStudentSerializer,
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Subjects assigned successfully",
                examples=[
                    OpenApiExample(
                        "Success response",
                        value={
                            "message": "Subjects assigned successfully",
                            "student_id": "uuid",
                            "count": 5,
                        },
                    ),
                ],
            ),
            400: OpenApiResponse(description="Validation error"),
            404: OpenApiResponse(description="Student not found"),
        },
    ),

    # ✅ NEW: Promote / Demote Students
    promote_students=extend_schema(
        tags=["Admin Management"],
        summary="Promote or demote multiple students",
        description=(
            "Promote or demote multiple students to a target class and academic session.\n\n"
            "### Request Body\n"
            "- `student_ids` (list[int]): IDs of students to promote/demote\n"
            "- `target_class_id` (int): Target class ID\n"
            "- `academic_session_id` (int): Target academic session ID\n"
            "- `reason` (str, optional): Reason for promotion/demotion\n\n"
            "**Permissions:** Principal / School Owner only.\n"
            "**Multi-tenant safe:** Students must belong to the same school."
        ),
        request=StudentPromotionSerializer,
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Students promoted successfully",
                examples=[
                    OpenApiExample(
                        "Success response",
                        value={
                            "message": "Students promoted successfully",
                            "promoted_count": 3,
                            "assignments": [
                                {"student_id": 1, "classroom": "Grade 3A", "session": "2025/2026"},
                                {"student_id": 2, "classroom": "Grade 3A", "session": "2025/2026"},
                                {"student_id": 3, "classroom": "Grade 3A", "session": "2025/2026"},
                            ],
                        },
                    ),
                ],
            ),
            400: OpenApiResponse(description="Validation error"),
            404: OpenApiResponse(description="Student not found"),
            403: OpenApiResponse(description="Permission denied"),
        },
    ),
)
# -------------------------------------------------------
#   AssessmentRecordViewSet Schema
# -------------------------------------------------------
AssessmentRecordSchema = extend_schema_view(
    list=extend_schema(
        summary="List Assessment Records",
        description=(
            "Returns all assessment records for students belonging to the "
            "authenticated user's school.\n\n"
            "### What the frontend should know:\n"
            "- You do NOT need to pass any parameters.\n"
            "- Only records from the teacher’s school are returned.\n"
            "- Useful for admin dashboards and teacher history pages."
        ),
        tags=["Assessment Records"],
    ),
    retrieve=extend_schema(
        summary="Retrieve a Single Assessment Record",
        description=(
            "Fetch detailed information about a specific assessment record.\n"
            "Pass the record ID in the URL (e.g., `/assessment-records/25/`)."
        ),
        tags=["Assessment Records"],
    ),
    create=extend_schema(
        summary="Create an Assessment Record",
        description=(
            "Creates a new assessment record for a single student.\n\n"
            "### Required Fields:\n"
            "- `student`: Student ID\n"
            "- `classroom_subject`: ID linking classroom → subject\n"
            "- `assessment_type`: e.g. Test, Assignment, Project\n"
            "- `index`: Attempt number (1..assessment_type.count)\n"
            "- `raw_score`: Score obtained\n\n"
            "### Notes:\n"
            "- `percentage_score` is automatically computed.\n"
            "- You cannot exceed the maximum allowed attempts."
        ),
        tags=["Assessment Records"],
        examples=[
            OpenApiExample(
                "Create Assessment Record Example",
                value={
                    "student": 15,
                    "classroom_subject": 8,
                    "assessment_type": 3,
                    "index": 1,
                    "raw_score": 18,
                },
            ),
        ],
    ),
    update=extend_schema(
        summary="Update an Assessment Record",
        description="Replaces an entire assessment record.",
        tags=["Assessment Records"],
    ),
    partial_update=extend_schema(
        summary="Partially Update an Assessment Record",
        description="Update one or more fields — e.g., only `raw_score`.",
        tags=["Assessment Records"],
    ),
    destroy=extend_schema(
        summary="Delete an Assessment Record",
        description="Deletes an assessment record by ID.",
        tags=["Assessment Records"],
    ),
)


# -------------------------------------------------------
#   AssessmentEntryFormDataView Schema
# -------------------------------------------------------
AssessmentEntryFormDataSchema = extend_schema_view(
    post=extend_schema(
        summary="Get Assessment Entry Form Data",
        description=(
            "Prepares all data required to load a teacher’s mark-entry form.\n\n"
            "### The frontend MUST send:\n"
            "- `class_room_id`: ID of the classroom\n"
            "- `subject_id`: ID of the subject\n\n"
            "### The endpoint returns:\n"
            "- Classroom info\n"
            "- Subject info\n"
            "- List of **active students** in the class\n"
            "- Assessment types configured by the school (e.g., Test, Assignment)\n\n"
            "### Intended Use:\n"
            "- Call this endpoint before entering scores to build the UI form.\n"
            "- Use `assessment_types.count` to determine number of attempts "
            "(e.g., Test 1, Test 2)."
        ),
        tags=["Assessment Records"],
        examples=[
            OpenApiExample(
                "Request Body Example",
                value={"class_room_id": 2, "subject_id": 5},
            ),
            OpenApiExample(
                "Successful Response Example",
                value={
                    "class_room": {"id": 2, "name": "JSS 2A"},
                    "subject": {"id": 5, "name": "Mathematics"},
                    "students": [
                        {"id": 1, "name": "John Doe", "student_id": "STU-001"},
                        {"id": 2, "name": "Jane Smith", "student_id": "STU-002"},
                    ],
                    "assessment_types": [
                        {"id": 3, "name": "Test", "count": 2, "max_score": 20},
                        {"id": 4, "name": "Assignment", "count": 1, "max_score": 10},
                    ],
                },
            ),
        ],
    ),
)


# -------------------------------------------------------
#   BulkAssessmentEntryView Schema
# -------------------------------------------------------
BulkAssessmentEntrySchema = extend_schema_view(
    post=extend_schema(
        summary="Bulk Create or Update Student Assessment Records",
        description=(
            "Enables teachers to submit assessment scores for multiple students at once.\n\n"
            "### Required Fields:\n"
            "- `classroom_subject_id`: ID linking class → subject\n"
            "- `assessment_type_id`: ID of assessment type\n"
            "- `entries`: Array of student score objects\n\n"
            "### `entries` Format:\n"
            "Each entry must contain:\n"
            "- `student_id`: Student ID\n"
            "- `index`: Attempt number\n"
            "- `raw_score`: Score obtained\n\n"
            "### Validation Rules:\n"
            "- Teacher must belong to the same school.\n"
            "- Students must belong to the classroom.\n"
            "- `index` must NOT exceed `assessment_type.count`.\n"
            "- `raw_score` must NOT exceed `assessment_type.max_score`.\n\n"
            "### Typical Use Case:\n"
            "- Submitting Test 1 scores for an entire class."
        ),
        tags=["Assessment Records"],
        examples=[
            OpenApiExample(
                "Bulk Assessment Payload Example",
                value={
                    "classroom_subject_id": 12,
                    "assessment_type_id": 3,
                    "entries": [
                        {"student_id": 1, "index": 1, "raw_score": 15},
                        {"student_id": 2, "index": 1, "raw_score": 18},
                        {"student_id": 3, "index": 1, "raw_score": 12},
                    ],
                },
            ),
            OpenApiExample(
                "Bulk Successful Response Example",
                value={
                    "created": 3,
                    "updated": 0,
                    "details": [
                        {"student_id": 1, "percentage": 75},
                        {"student_id": 2, "percentage": 90},
                        {"student_id": 3, "percentage": 60},
                    ],
                },
            ),
        ],
    ),
)


teachers_dashboard = extend_schema_view(

    # =====================================================
    # STEP 1 — Teacher Dashboard Entry Point
    # =====================================================
    classes=extend_schema(
        summary="List teacher assigned classrooms",
        description=(
            "STEP 1: Fetch classrooms assigned to the logged-in teacher.\n\n"
            "This endpoint returns only classrooms the teacher is allowed to access "
            "based on teaching assignments and school scope.\n\n"
            "**Frontend flow:**\n"
            "1. Call this endpoint immediately after teacher login.\n"
            "2. Populate the dashboard classroom cards or class switcher dropdown.\n"
            "3. Use the returned `id` to fetch students in a classroom.\n\n"
            "**Permissions:** Teacher must be assigned to the classroom."
        ),
        responses={200: TeacherClassroomSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 2 — Classroom → Student List
    # =====================================================
    students=extend_schema(
        summary="List students in a classroom",
        description=(
            "STEP 2: Fetch students enrolled in a specific classroom.\n\n"
            "Returns a lightweight student list suitable for tables and lists.\n\n"
            "**Frontend flow:**\n"
            "1. Teacher selects a classroom.\n"
            "2. Call this endpoint with `classroom_id`.\n"
            "3. Render student roster (name, ID, email).\n"
            "4. Clicking a student navigates to the student profile screen."
        ),
        parameters=[
            OpenApiParameter(
                name="classroom_id",
                description="Unique classroom identifier",
                required=True,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: ClassroomStudentSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 3 — Student Profile Overview
    # =====================================================
    student_profile=extend_schema(
        summary="Retrieve student profile details",
        description=(
            "STEP 3: Fetch full student profile information.\n\n"
            "Provides demographic and academic placement details for a student.\n\n"
            "**Frontend flow:**\n"
            "1. User clicks a student from the classroom list.\n"
            "2. Call this endpoint using `student_id`.\n"
            "3. Render student profile header and personal info section.\n\n"
            "**Use cases:**\n"
            "- Student profile page\n"
            "- Teacher review screens\n"
            "- Admin oversight"
        ),
        parameters=[
            OpenApiParameter(
                name="student_id",
                description="Public student identifier",
                required=True,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: StudentProfileDetailSerializer},
        tags=["Teacher Dashboard"],
    ),

    subjects=extend_schema(
        summary="List subjects taught by the teacher",
        description=(
            "STEP 4: Fetch subjects assigned to the logged-in teacher along with classroom, "
            "current academic session, and term.\n\n"
            "**Frontend flow:**\n"
            "1. Call this endpoint after fetching classrooms.\n"
            "2. Render subjects per classroom.\n"
            "3. Use this information to link to assessment entry or subject results.\n\n"
            "**Permissions:** Teacher must have a teaching assignment.\n\n"
            "**Notes:** Optimized with select_related to avoid N+1 queries; session and term "
            "are injected via context."
        ),
        responses={200: TeacherSubjectClassTermSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),


    # =====================================================
    # STEP 3A — Teacher Subjects (NEW)
    # =====================================================
    list_teacher_subjects=extend_schema(
        summary="List subjects taught by the logged-in teacher",
        description=(
            "STEP 3A: Fetch subjects the teacher is authorized to teach.\n\n"
            "This endpoint is derived from TeachingAssignment and returns "
            "subjects scoped by classroom.\n\n"
            "**Frontend flow:**\n"
            "1. Call this before assessment entry.\n"
            "2. Populate subject dropdowns per classroom.\n"
            "3. Prevent teachers from selecting unauthorized subjects.\n\n"
            "**Notes:**\n"
            "- Each subject is tied to a classroom.\n"
            "- Only active subjects are returned."
        ),
        parameters=[
            OpenApiParameter(
                name="classroom",
                description="Optional classroom filter",
                required=False,
                location=OpenApiParameter.QUERY,
            ),
        ],
        responses={200: TeacherSubjectSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 3B — Assessment Types (NEW)
    # =====================================================
    list_assessment_types=extend_schema(
        summary="List assessment types for the active academic term",
        description=(
            "STEP 3B: Fetch assessment types configured for the active academic term.\n\n"
            "Assessment types are policy-driven and define:\n"
            "- Allowed assessment categories (CA, Exam, Project, etc.)\n"
            "- Score limits\n"
            "- Weighting rules\n\n"
            "**Frontend flow:**\n"
            "1. Call this before submitting assessment entries.\n"
            "2. Populate assessment type selector.\n"
            "3. Use `max_score` and `count` for client-side hints.\n\n"
            "**Important:**\n"
            "All enforcement is still validated server-side."
        ),
        responses={200: AssessmentTypeSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 4 — Raw Assessment Entries
    # =====================================================
    student_assessments=extend_schema(
        summary="Retrieve student assessment entries",
        description=(
            "STEP 4: Fetch raw assessment records for a student.\n\n"
            "Each record represents an individual assessment entry "
            "(CA, test, exam, quiz, etc).\n\n"
            "**Frontend flow:**\n"
            "1. Load this when displaying subject score breakdowns.\n"
            "2. Use to render tables, charts, and progress analytics.\n"
            "3. Optionally filter by subject.\n\n"
            "**Notes:**\n"
            "- Scores are raw values.\n"
            "- Percentages are computed server-side."
        ),
        parameters=[
            OpenApiParameter(
                name="student_id",
                description="Public student identifier",
                required=True,
                location=OpenApiParameter.PATH,
            ),
            OpenApiParameter(
                name="subject_id",
                description="Optional subject filter",
                required=False,
                location=OpenApiParameter.QUERY,
            ),
        ],
        responses={200: AssessmentEntrySerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 5 — Computed Subject Results
    # =====================================================
    student_subject_results=extend_schema(
        summary="Retrieve computed subject results",
        description=(
            "STEP 5: Fetch fully computed subject results for a student.\n\n"
            "This endpoint returns aggregated academic results including:\n"
            "- Continuous assessment totals\n"
            "- Exam scores\n"
            "- Final grade and remarks\n\n"
            "**Frontend flow:**\n"
            "1. Call after loading raw assessments.\n"
            "2. Display final grades per subject.\n"
            "3. Use for report cards and academic summaries.\n\n"
            "**Important:**\n"
            "This data is computed and validated by backend services."
        ),
        parameters=[
            OpenApiParameter(
                name="student_id",
                description="Public student identifier",
                required=True,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: SubjectResultSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 6 — Subject + Assessment Composite View
    # =====================================================
    student_subject_breakdown=extend_schema(
        summary="Retrieve subject-wise assessment breakdown",
        description=(
            "STEP 6: Fetch subject-centric academic breakdown.\n\n"
            "This endpoint combines:\n"
            "- Subject information\n"
            "- Individual assessment entries\n"
            "- Final computed subject result\n\n"
            "**Frontend flow:**\n"
            "1. Use for detailed subject drill-down pages.\n"
            "2. Ideal for accordion or tab-based subject views.\n"
            "3. Prevents multiple API calls per subject."
        ),
        parameters=[
            OpenApiParameter(
                name="student_id",
                description="Public student identifier",
                required=True,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: StudentSubjectResultSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 7 — Guardian / Emergency Contacts
    # =====================================================
    student_contacts=extend_schema(
        summary="Retrieve student guardian and contact details",
        description=(
            "STEP 7: Fetch guardian and emergency contact information.\n\n"
            "Returns all registered contacts ordered by priority.\n\n"
            "**Frontend flow:**\n"
            "1. Display guardian cards on student profile.\n"
            "2. Enable call, email, or emergency actions.\n"
            "3. Highlight primary guardian."
        ),
        parameters=[
            OpenApiParameter(
                name="student_id",
                description="Public student identifier",
                required=True,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: StudentContactSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 8 — Result Snapshots / Reports
    # =====================================================
    result_snapshots=extend_schema(
        summary="Retrieve generated result snapshots",
        description=(
            "STEP 8: Fetch frozen academic reports for a student.\n\n"
            "Represents generated PDFs or exports for specific terms.\n\n"
            "**Frontend flow:**\n"
            "1. Display downloadable report history.\n"
            "2. Allow viewing or downloading PDF reports.\n"
            "3. Prevent regeneration conflicts."
        ),
        parameters=[
            OpenApiParameter(
                name="student_id",
                description="Public student identifier",
                required=True,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: ResultSnapshotSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 9 — Students in teacher's classrooms by subjects
    # =====================================================
    students_by_subject=extend_schema(
        summary="List students in teacher-assigned classrooms matching teacher subjects",
        description=(
            "STEP 9: Fetch all students who are in classrooms assigned to the logged-in teacher "
            "and are enrolled in at least one subject that the teacher teaches.\n\n"
            "**Frontend flow:**\n"
            "1. Call this endpoint to populate student lists filtered by subject.\n"
            "2. Use for assessment entry or subject-specific dashboards.\n"
            "3. Returns matched subjects per student for display.\n\n"
            "**Permissions:** Teacher must be assigned to the classroom and subject."
        ),
        responses={200: StudentSubjectMatchSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),

    # =====================================================
    # STEP 3C — Enter Single Assessment (NEW)
    # =====================================================
    # enter_assessment=extend_schema(
    #     summary="Enter a single assessment record",
    #     description=(
    #         "STEP 3C: Create a single assessment entry for a student.\n\n"
    #         "This endpoint allows a teacher to submit one assessment score "
    #         "for a specific student and subject.\n\n"
    #         "**Flow:**\n"
    #         "1. Teacher selects classroom.\n"
    #         "2. Teacher selects subject.\n"
    #         "3. Teacher selects student.\n"
    #         "4. Teacher selects assessment type (CA, Exam, etc).\n"
    #         "5. Teacher submits score.\n\n"
    #         "**Server-side validations include:**\n"
    #         "- Teacher must be assigned to the classroom.\n"
    #         "- Teacher must be assigned to teach the subject.\n"
    #         "- Student must be enrolled in subject.\n"
    #         "- Term must be active.\n"
    #         "- Score must not exceed allowed limits.\n"
    #         "- Assessment count policy enforcement.\n\n"
    #         "**Side Effect:**\n"
    #         "Subject results are automatically recomputed after successful entry."
    #     ),
    #     request=AssessmentEntryCreateSerializer,
    #     responses={
    #         201: AssessmentEntrySerializer,
    #         400: OpenApiResponse(description="Validation error"),
    #         403: OpenApiResponse(description="Permission denied"),
    #     },
    #     tags=["Teacher Dashboard"],
    # ),

    # # =====================================================
    # # STEP 3D — Enter Bulk Assessments (NEW)
    # # =====================================================
    # enter_bulk_assessments=extend_schema(
    #     summary="Enter multiple assessment records in bulk",
    #     description=(
    #         "STEP 3D: Create multiple assessment entries in one request.\n\n"
    #         "This endpoint is optimized for bulk score entry "
    #         "(e.g., entering CA scores for an entire class).\n\n"
    #         "**Request structure:**\n"
    #         "- `subject_id`: Common subject for all entries.\n"
    #         "- `entries`: List of student assessment payloads.\n\n"
    #         "**Each entry must contain:**\n"
    #         "- `student_id`\n"
    #         "- `assessment_type_id`\n"
    #         "- `score`\n\n"
    #         "**Server-side validations include:**\n"
    #         "- Teacher classroom authorization per student.\n"
    #         "- Subject assignment validation.\n"
    #         "- Enrollment verification.\n"
    #         "- Term activity check.\n"
    #         "- Score limit enforcement.\n"
    #         "- Cumulative policy enforcement.\n\n"
    #         "**Transaction behavior:**\n"
    #         "- All entries are processed atomically.\n"
    #         "- If one entry fails, the entire request is rolled back.\n\n"
    #         "**Side Effect:**\n"
    #         "Subject results are recomputed for each affected student."
    #     ),
    #     request=BulkAssessmentEntrySerializer,
    #     responses={
    #         201: AssessmentEntrySerializer(many=True),
    #         400: OpenApiResponse(description="Validation error"),
    #         403: OpenApiResponse(description="Permission denied"),
    #     },
    #     tags=["Teacher Dashboard"],
    # ),
)


accessment_record_schema = extend_schema_view(
    create=extend_schema(
        summary="Bulk Assessment Entry",
        description=(
            "Create multiple assessment records in bulk. "
            "Validates student enrollment, teacher assignment, and assessment score. "
            "Computes subject results and term summaries after saving."
        ),
        request=BulkAssessmentEntrySerializer,
        responses={201: AssessmentEntrySerializer(many=True)},
    ),
    list=extend_schema(
        summary="List Assessment Records",
        description="Retrieve assessment records. Can filter by student_id, classroom_id, subject_id, or term_id.",
        parameters=[
            OpenApiParameter(name="student_id", description="Filter by student ID", required=False, type=int),
            OpenApiParameter(name="classroom_id", description="Filter by classroom ID", required=False, type=int),
            OpenApiParameter(name="subject_id", description="Filter by subject ID", required=False, type=int),
            OpenApiParameter(name="term_id", description="Filter by term ID", required=False, type=int),
        ],
        responses={200: AssessmentEntrySerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve Assessment Record",
        description="Retrieve a single assessment record by ID.",
        responses={200: AssessmentEntrySerializer},
    ),
    update=extend_schema(
        summary="Update Assessment Record",
        description="Update an existing assessment record. Validates score and enrollment.",
        request=AssessmentEntryCreateSerializer,
        responses={200: AssessmentEntrySerializer},
    ),
    partial_update=extend_schema(
        summary="Partial Update Assessment Record",
        description="Update one or more fields of an assessment record.",
        request=AssessmentEntryCreateSerializer,
        responses={200: AssessmentEntrySerializer},
    ),
)
