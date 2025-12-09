from rest_framework import serializers

from core.applications.users.models import TeacherProfile

class TeacherProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")

    class Meta:
        model = TeacherProfile
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "qualification",
            "specialization",
            "department",
            "staff_id",
        ]
