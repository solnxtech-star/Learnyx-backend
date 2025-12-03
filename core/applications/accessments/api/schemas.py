from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from core.applications.users.api.serializers.admin_serializers import (
    ClassRoomSerializer,
    ClassRoomCreateSerializer,
)
from core.applications.accessments.api.serializers.academic_serializers import (
    AcademicSessionSerializer,
    AcademicTermSerializer,
)
from core.applications.timetable.api.serializers import SubjectSerializer


UnifiedAcademicsSchema = extend_schema_view(

    # ------------------------------------
    # CLASSROOMS CRUD
    # ------------------------------------
    classrooms=extend_schema(
        tags=["Academics • Classrooms"],
        summary="List Classrooms",
        description="Retrieve all classrooms for the authenticated user's school.",
        responses=ClassRoomSerializer(many=True),
    ),

    create_classroom=extend_schema(
        tags=["Academics • Classrooms"],
        summary="Create Classroom",
        request=ClassRoomCreateSerializer,
        responses={201: ClassRoomSerializer},
    ),

    get_classroom=extend_schema(
        tags=["Academics • Classrooms"],
        summary="Retrieve Classroom",
        parameters=[
            OpenApiParameter(
                name="pk",
                type=str,
                location=OpenApiParameter.PATH,
                description="Classroom ID to retrieve",
            )
        ],
        responses={200: ClassRoomSerializer, 404: None},
    ),

    update_classroom=extend_schema(
        tags=["Academics • Classrooms"],
        summary="Update Classroom",
        request=ClassRoomCreateSerializer,
        responses={200: ClassRoomSerializer, 404: None},
    ),

    delete_classroom=extend_schema(
        tags=["Academics • Classrooms"],
        summary="Delete Classroom",
        responses={204: None, 404: None},
    ),

    # ------------------------------------
    # ACADEMIC SESSIONS
    # ------------------------------------
    list_sessions=extend_schema(
        tags=["Academics • Sessions"],
        summary="List Academic Sessions",
        responses=AcademicSessionSerializer(many=True),
    ),

    create_session=extend_schema(
        tags=["Academics • Sessions"],
        summary="Create Academic Session",
        request=AcademicSessionSerializer,
        responses={201: AcademicSessionSerializer},
    ),

    # ------------------------------------
    # ACADEMIC TERMS
    # ------------------------------------
    list_terms=extend_schema(
        tags=["Academics • Terms"],
        summary="List Academic Terms",
        parameters=[
            OpenApiParameter(
                name="session_id",
                type=str,
                required=True,
                location=OpenApiParameter.QUERY,
                description="Filter by academic session",
            )
        ],
        responses=AcademicTermSerializer(many=True),
    ),

    create_term=extend_schema(
        tags=["Academics • Terms"],
        summary="Create Academic Term",
        request=AcademicTermSerializer,
        responses={201: AcademicTermSerializer},
    ),

    # ------------------------------------
    # SUBJECTS
    # ------------------------------------
    list_subjects=extend_schema(
        tags=["Academics • Subjects"],
        summary="List Subjects",
        parameters=[
            OpenApiParameter(
                name="search",
                type=str,
                required=False,
                location=OpenApiParameter.QUERY,
                description="Filter subjects by name search",
            )
        ],
        responses=SubjectSerializer(many=True),
    ),

    create_subject=extend_schema(
        tags=["Academics • Subjects"],
        summary="Create Subject",
        request=SubjectSerializer,
        responses={201: SubjectSerializer},
    ),
)
