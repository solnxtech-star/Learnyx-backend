from drf_spectacular.utils import extend_schema

from core.applications.academics.api.serializers import AssignClassRoomSerializer
from core.applications.users.api.serializers.serializers import TeacherProfileSerializer

assign_teacher_classroom_schema = extend_schema(
    summary="Assign or update a teacher's classroom",
    description=(
        "Allows a **Principal** or **School Owner** to assign a classroom "
        "to a teacher.\n\n"
        "### Example Body\n"
        "```\n"
        "{\n"
        '  "classroom_id": "4a3b1c4e-12ab-44cd-93ab-ae29fefd11e3"\n'
        "}\n"
        "```\n"
        "### Notes\n"
        "- Teacher must belong to the same school.\n"
        "- Classroom must also belong to the same school.\n"
        "- This action REPLACES previously assigned classroom.\n"
    ),
    request=AssignClassRoomSerializer,
    responses={200: TeacherProfileSerializer},
)
