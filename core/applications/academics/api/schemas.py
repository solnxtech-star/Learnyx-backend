from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view

from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    ClassroomStudentSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentAssessmentSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentContactSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    StudentProfileDetailSerializer,
)
from core.applications.academics.api.serializers.teachers_dashboard_serializers import (
    TeacherClassroomSerializer,
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
    classes=extend_schema(
        summary="Get teacher classrooms",
        description=(
            "Returns a list of classrooms assigned to the logged-in teacher.\n\n"
            "**Frontend usage:**\n"
            "Use this endpoint to populate the teacher's classroom list on the dashboard "
            "or classroom switcher dropdown."
        ),
        responses={200: TeacherClassroomSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),
    students=extend_schema(
        summary="Get students in classroom",
        description=(
            "Returns a list of students enrolled in a specific classroom.\n\n"
            "**Frontend usage:**\n"
            "Use this endpoint to render class rosters when a teacher opens a classroom."
        ),
        parameters=[
            OpenApiParameter(
                name="classroom_id",
                description="Unique ID of the classroom",
                required=True,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: ClassroomStudentSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),
    student_profile=extend_schema(
        summary="Get detailed student profile",
        description=(
            "Returns full profile information of a student.\n\n"
            "**Frontend usage:**\n"
            "Use this endpoint when viewing a student's detailed information page."
        ),
        parameters=[
            OpenApiParameter(
                name="student_id",
                description="Unique student ID",
                required=True,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: StudentProfileDetailSerializer},
        tags=["Teacher Dashboard"],
    ),
    student_assessments=extend_schema(
        summary="Get student assessments",
        description=(
            "Returns all assessment records for a student.\n\n"
            "**Frontend usage:**\n"
            "Use this endpoint to render results tables, charts, and performance analytics.\n"
            "Optional query param: `subject_id` for subject-specific filtering."
        ),
        parameters=[
            OpenApiParameter(
                name="student_id",
                description="Unique student ID",
                required=True,
                location=OpenApiParameter.PATH,
            ),
            OpenApiParameter(
                name="subject_id",
                description="Optional subject ID for filtering results",
                required=False,
                location=OpenApiParameter.QUERY,
            ),
        ],
        responses={200: StudentAssessmentSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),
    student_contacts=extend_schema(
        summary="Get student guardian/contacts",
        description=(
            "Returns guardian and emergency contact details.\n\n"
            "**Frontend usage:**\n"
            "Use this endpoint to render guardian contact cards and emergency call actions."
        ),
        parameters=[
            OpenApiParameter(
                name="student_id",
                description="Unique student ID",
                required=True,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={200: StudentContactSerializer(many=True)},
        tags=["Teacher Dashboard"],
    ),
)
