from rest_framework import serializers

from core.applications.academics.models import ClassRoom, TeachingAssignment


class AssignClassRoomSerializer(serializers.Serializer):
    """
    Admin assigns multiple classrooms to a teacher.
    """
    classroom_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        required=True,
        help_text="List of classroom IDs"
    )

    def validate_classroom_ids(self, classroom_ids):
        request = self.context["request"]
        school = request.user.school

        classrooms = ClassRoom.objects.filter(
            id__in=classroom_ids,
            school=school
        )

        if classrooms.count() != len(classroom_ids):
            raise serializers.ValidationError(
                "One or more classroom IDs are invalid for this school."
            )

        return classrooms

    def save(self, teacher_profile):
        classrooms = self.validated_data["classroom_ids"]
        teacher_profile.classrooms.set(classrooms)
        return teacher_profile



class TeachingAssignmentSerializer(serializers.Serializer):
    """
    Teacher assigns themselves to multiple classrooms and subjects.
    """
    classroom_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        required=True
    )
    subject_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        required=True
    )

    def validate(self, attrs):
        teacher = self.context["teacher"]
        school = teacher.school

        # Validate classrooms
        classrooms = ClassRoom.objects.filter(
            id__in=attrs["classroom_ids"],
            school=school
        )
        if classrooms.count() != len(attrs["classroom_ids"]):
            raise serializers.ValidationError("Invalid classroom IDs.")

        # Validate subjects
        subjects = Subject.objects.filter(
            id__in=attrs["subject_ids"],
            school=school
        )
        if subjects.count() != len(attrs["subject_ids"]):
            raise serializers.ValidationError("Invalid subject IDs.")

        attrs["classrooms"] = classrooms
        attrs["subjects"] = subjects
        return attrs

    def create(self, validated_data):
        teacher = self.context["teacher"]
        assignments = []

        for classroom in validated_data["classrooms"]:
            for subject in validated_data["subjects"]:
                assignments.append(
                    TeachingAssignment.objects.create(
                        teacher=teacher,
                        classroom=classroom,
                        subject=subject
                    )
                )
        return assignments
