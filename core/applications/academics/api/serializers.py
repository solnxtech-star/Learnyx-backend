from rest_framework import serializers
from core.applications.academics.models import ClassRoom
from core.applications.users.models import TeacherProfile

class AssignClassRoomSerializer(serializers.Serializer):
    """
    Used by admin to assign or update a teacher's classroom.
    """
    classroom_id = serializers.UUIDField(required=True)

    def validate_classroom_id(self, classroom_id):
        request = self.context["request"]
        user_school = request.user.school

        classroom = ClassRoom.objects.filter(
            id=classroom_id,
            school=user_school
        ).first()

        if not classroom:
            raise serializers.ValidationError("Invalid classroom_id for this school.")

        return classroom

    def save(self, teacher_profile):
        classroom = self.validated_data["classroom_id"]
        teacher_profile.classroom = classroom
        teacher_profile.save(update_fields=["classroom"])
        return teacher_profile