from core.applications.academics.api.schemas import AssessmentEntryFormDataSchema, AssessmentRecordSchema, BulkAssessmentEntrySchema
from core.applications.academics.api.serializers.accessment_entry_serializers import AssessmentEntryFormDataSerializer, AssessmentRecordSerializer, BulkAssessmentEntrySerializer
from core.applications.academics.models import AssessmentRecord, AssessmentType
from core.applications.users.models import StudentProfile
from core.helper.permissions import IsPrincipalOwnerOrAssignedTeacher
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from django.db import transaction
from rest_framework.viewsets import ViewSet



@AssessmentRecordSchema
class AssessmentRecordViewSet(viewsets.ModelViewSet):
    """
    CRUD for individual assessment records.
    """
    serializer_class = AssessmentRecordSerializer
    permission_classes = [IsAuthenticated, IsPrincipalOwnerOrAssignedTeacher]

    def get_queryset(self):
        school = self.request.user.school
        return AssessmentRecord.objects.filter(
            student__school=school
        ).select_related(
            "student", "classroom_subject", "assessment_type"
        )

    def perform_create(self, serializer):
        return serializer.save()

    def perform_update(self, serializer):
        return serializer.save()

@AssessmentEntryFormDataSchema
class AssessmentEntryViewSet(ViewSet):
    """
    Loads the data needed for teacher assessment entry form.
    """
    permission_classes = [IsAuthenticated, IsPrincipalOwnerOrAssignedTeacher]

    def create(self, request, *args, **kwargs):
        serializer = AssessmentEntryFormDataSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        class_room = serializer.validated_data["class_room"]
        subject = serializer.validated_data["subject"]
        school = request.user.school

        students = StudentProfile.objects.filter(
            class_room=class_room, school=school, is_active=True
        )

        assessment_types = AssessmentType.objects.filter(
            policy__school=school
        )

        return Response({
            "class_room": {"id": class_room.id, "name": class_room.name},
            "subject": {"id": subject.id, "name": subject.name},
            "students": [
                {
                    "id": s.id,
                    "name": s.user.name,
                    "student_id": s.student_id,
                }
                for s in students
            ],
            "assessment_types": [
                {
                    "id": a.id,
                    "name": a.name,
                    "count": a.count,
                    "max_score": a.max_score,
                }
                for a in assessment_types
            ],
        })


@BulkAssessmentEntrySchema
class BulkAssessmentEntryViewSet(ViewSet):
    """
    Handles bulk creation/update of assessment records.
    """
    permission_classes = [IsAuthenticated, IsPrincipalOwnerOrAssignedTeacher]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = BulkAssessmentEntrySerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result, status=status.HTTP_200_OK)
